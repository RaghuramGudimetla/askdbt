"""Embed model chunks and store in the configured vector database."""

from __future__ import annotations

import hashlib
import uuid
from typing import TYPE_CHECKING

from sentence_transformers import SentenceTransformer

from .config import Config, get_config
from .parser import ModelChunk

if TYPE_CHECKING:
    pass


def _chunk_id(model_id: str) -> str:
    """Stable UUID from model_id so re-indexing is idempotent."""
    hex_digest = hashlib.md5(model_id.encode()).hexdigest()
    return str(uuid.UUID(hex_digest))


class Indexer:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self._embedder: SentenceTransformer | None = None

    def _get_embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            self._embedder = SentenceTransformer(self.config.embedding_model)
        return self._embedder

    def index(self, chunks: list[ModelChunk], show_progress: bool = True, recreate: bool = False) -> int:
        """Embed chunks and upsert into the vector store. Returns count indexed."""
        embedder = self._get_embedder()
        texts = [chunk.to_text() for chunk in chunks]

        if show_progress:
            print(f"  Embedding {len(chunks)} models with {self.config.embedding_model}...")

        vectors = embedder.encode(texts, show_progress_bar=show_progress, convert_to_numpy=True)

        if self.config.vector_db == "qdrant":
            return self._upsert_qdrant(chunks, vectors, recreate=recreate)
        elif self.config.vector_db == "pgvector":
            return self._upsert_pgvector(chunks, vectors, recreate=recreate)
        else:
            raise ValueError(f"Unknown vector_db: {self.config.vector_db}")

    def _upsert_qdrant(self, chunks: list[ModelChunk], vectors, recreate: bool = False) -> int:
        from qdrant_client import QdrantClient
        from qdrant_client.models import Distance, PointStruct, VectorParams

        client = QdrantClient(host=self.config.qdrant_host, port=self.config.qdrant_port)

        existing = [c.name for c in client.get_collections().collections]
        if recreate and self.config.qdrant_collection in existing:
            client.delete_collection(self.config.qdrant_collection)
            existing.remove(self.config.qdrant_collection)

        if self.config.qdrant_collection not in existing:
            client.create_collection(
                collection_name=self.config.qdrant_collection,
                vectors_config=VectorParams(size=self.config.embedding_dim, distance=Distance.COSINE),
            )

        points = [
            PointStruct(
                id=_chunk_id(chunk.model_id),
                vector=vec.tolist(),
                payload={
                    **chunk.to_metadata(),
                    "model_id": chunk.model_id,
                    "text": chunk.to_text(),
                    "description": chunk.description,
                    "depends_on": chunk.depends_on,
                    "child_ids": chunk.child_ids,
                    "all_downstream_ids": chunk.all_downstream_ids,
                    "column_names": [c.name for c in chunk.columns],
                    "compiled_sql": chunk.compiled_sql or "",
                    "columns": [
                        {"name": c.name, "description": c.description, "data_type": c.data_type}
                        for c in chunk.columns
                    ],
                },
            )
            for chunk, vec in zip(chunks, vectors)
        ]

        client.upsert(collection_name=self.config.qdrant_collection, points=points)
        return len(points)

    def _upsert_pgvector(self, chunks: list[ModelChunk], vectors, recreate: bool = False) -> int:
        import json

        import psycopg2
        from psycopg2.extras import execute_values

        conn = psycopg2.connect(self.config.pg_dsn)
        cur = conn.cursor()
        cur.execute("CREATE EXTENSION IF NOT EXISTS vector")
        if recreate:
            cur.execute(f"DROP TABLE IF EXISTS {self.config.pg_table}")
        cur.execute(f"""
            CREATE TABLE IF NOT EXISTS {self.config.pg_table} (
                id                  TEXT PRIMARY KEY,
                model_id            TEXT NOT NULL,
                model_name          TEXT NOT NULL,
                text                TEXT NOT NULL,
                metadata            JSONB,
                depends_on          TEXT[],
                child_ids           TEXT[],
                all_downstream_ids  TEXT[],
                column_names        TEXT[],
                compiled_sql        TEXT,
                embedding           vector({self.config.embedding_dim})
            )
        """)

        rows = [
            (
                _chunk_id(chunk.model_id),
                chunk.model_id,
                chunk.model_name,
                chunk.to_text(),
                json.dumps(chunk.to_metadata()),
                chunk.depends_on,
                chunk.child_ids,
                chunk.all_downstream_ids,
                [c.name for c in chunk.columns],
                chunk.compiled_sql or "",
                vec.tolist(),
            )
            for chunk, vec in zip(chunks, vectors)
        ]

        execute_values(
            cur,
            f"""
            INSERT INTO {self.config.pg_table}
                (id, model_id, model_name, text, metadata, depends_on, child_ids,
                 all_downstream_ids, column_names, compiled_sql, embedding)
            VALUES %s
            ON CONFLICT (id) DO UPDATE SET
                text               = EXCLUDED.text,
                metadata           = EXCLUDED.metadata,
                depends_on         = EXCLUDED.depends_on,
                child_ids          = EXCLUDED.child_ids,
                all_downstream_ids = EXCLUDED.all_downstream_ids,
                column_names       = EXCLUDED.column_names,
                compiled_sql       = EXCLUDED.compiled_sql,
                embedding          = EXCLUDED.embedding
            """,
            rows,
            template="(%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)",
        )
        conn.commit()
        cur.close()
        conn.close()
        return len(rows)
