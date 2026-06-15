"""RAG retrieval: embed query, fetch top-k chunks, prompt Ollama."""

from __future__ import annotations

import json
from dataclasses import dataclass

import requests
from sentence_transformers import SentenceTransformer

from .config import Config, get_config


@dataclass
class RetrievedChunk:
    model_name: str
    text: str
    score: float


@dataclass
class Answer:
    question: str
    answer: str
    sources: list[str]


class Retriever:
    def __init__(self, config: Config | None = None):
        self.config = config or get_config()
        self._embedder: SentenceTransformer | None = None

    def _get_embedder(self) -> SentenceTransformer:
        if self._embedder is None:
            self._embedder = SentenceTransformer(self.config.embedding_model)
        return self._embedder

    def retrieve(self, query: str) -> list[RetrievedChunk]:
        vec = self._get_embedder().encode([query], convert_to_numpy=True)[0].tolist()

        if self.config.vector_db == "qdrant":
            return self._retrieve_qdrant(vec)
        elif self.config.vector_db == "pgvector":
            return self._retrieve_pgvector(vec)
        else:
            raise ValueError(f"Unknown vector_db: {self.config.vector_db}")

    def _retrieve_qdrant(self, vec: list[float]) -> list[RetrievedChunk]:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=self.config.qdrant_host, port=self.config.qdrant_port)
        response = client.query_points(
            collection_name=self.config.qdrant_collection,
            query=vec,
            limit=self.config.top_k,
            score_threshold=self.config.score_threshold,
            with_payload=True,
        )
        return [
            RetrievedChunk(
                model_name=r.payload.get("model_name", ""),
                text=r.payload.get("text", ""),
                score=r.score,
            )
            for r in response.points
        ]

    def _retrieve_pgvector(self, vec: list[float]) -> list[RetrievedChunk]:
        import psycopg2

        conn = psycopg2.connect(self.config.pg_dsn)
        cur = conn.cursor()
        cur.execute(
            f"""
            SELECT model_name, text, 1 - (embedding <=> %s::vector) AS score
            FROM {self.config.pg_table}
            WHERE 1 - (embedding <=> %s::vector) >= %s
            ORDER BY score DESC
            LIMIT %s
            """,
            (vec, vec, self.config.score_threshold, self.config.top_k),
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()
        return [RetrievedChunk(model_name=r[0], text=r[1], score=r[2]) for r in rows]

    def ask(self, question: str) -> Answer:
        meta = self._try_meta_answer(question)
        if meta is not None:
            return Answer(question=question, answer=meta, sources=[])

        chunks = self.retrieve(question)
        if not chunks:
            return Answer(
                question=question,
                answer="I could not find any relevant models in the index. Try re-running `askdbt index`.",
                sources=[],
            )

        context = "\n\n---\n\n".join(c.text for c in chunks)
        prompt = _build_prompt(question, context)
        answer_text = self._call_ollama(prompt)

        return Answer(
            question=question,
            answer=answer_text,
            sources=[c.model_name for c in chunks],
        )

    def _try_meta_answer(self, question: str) -> str | None:
        """Answer counting/listing questions directly from the vector store."""
        q = question.lower()
        is_count = any(w in q for w in ("how many", "count", "total number", "number of"))
        is_list = any(w in q for w in ("list", "what models", "which models", "show all", "all models"))
        is_deps = any(w in q for w in ("dependenc", "depends on", "upstream", "downstream", "lineage"))
        if not (is_count or is_list or is_deps):
            return None

        if self.config.vector_db == "qdrant":
            return self._meta_qdrant(is_count, is_deps)
        elif self.config.vector_db == "pgvector":
            return self._meta_pgvector(is_count, is_deps)
        return None

    def _meta_qdrant(self, count_only: bool, deps_only: bool) -> str:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=self.config.qdrant_host, port=self.config.qdrant_port)
        total = client.count(collection_name=self.config.qdrant_collection).count

        if count_only and not deps_only:
            return f"There are **{total} models** indexed in this dbt project."

        results, _ = client.scroll(
            collection_name=self.config.qdrant_collection,
            limit=total,
            with_payload=True,
        )

        if deps_only:
            return _format_dependencies(results)

        names = sorted(r.payload.get("model_name", "") for r in results)
        bullet_list = "\n".join(f"- {n}" for n in names)
        return f"There are **{total} models** in this dbt project:\n\n{bullet_list}"

    def _meta_pgvector(self, count_only: bool, deps_only: bool) -> str:
        import psycopg2

        conn = psycopg2.connect(self.config.pg_dsn)
        cur = conn.cursor()
        cur.execute(f"SELECT model_name, text FROM {self.config.pg_table} ORDER BY model_name")
        rows = cur.fetchall()
        cur.close()
        conn.close()
        total = len(rows)

        if count_only and not deps_only:
            return f"There are **{total} models** indexed in this dbt project."

        if deps_only:
            records = [type("R", (), {"payload": {"model_name": r[0], "text": r[1]}})() for r in rows]
            return _format_dependencies(records)

        names = [r[0] for r in rows]
        bullet_list = "\n".join(f"- {n}" for n in names)
        return f"There are **{total} models** in this dbt project:\n\n{bullet_list}"

    def _call_ollama(self, prompt: str) -> str:
        url = f"{self.config.ollama_base_url}/api/generate"
        payload = {
            "model": self.config.ollama_model,
            "prompt": prompt,
            "stream": False,
        }
        try:
            resp = requests.post(url, json=payload, timeout=120)
            resp.raise_for_status()
            return resp.json().get("response", "").strip()
        except requests.exceptions.ConnectionError:
            return (
                f"Could not connect to Ollama at {self.config.ollama_base_url}. "
                "Make sure Ollama is running: `ollama serve`"
            )
        except requests.exceptions.HTTPError as e:
            return f"Ollama returned an error: {e}"


def _format_dependencies(records) -> str:
    lines = []
    for r in sorted(records, key=lambda x: x.payload.get("model_name", "")):
        name = r.payload.get("model_name", "")
        deps = r.payload.get("depends_on")
        if deps is None:
            # Fall back to parsing from the embedded text
            for line in r.payload.get("text", "").splitlines():
                if line.startswith("Depends on:"):
                    raw = line.replace("Depends on:", "").strip()
                    deps = [d.strip() for d in raw.split(",") if d.strip()]
                    break
        if deps:
            lines.append(f"- **{name}** → {', '.join(deps)}")
        else:
            lines.append(f"- **{name}** (no upstream dependencies)")
    return "**Model dependencies:**\n\n" + "\n".join(lines)


def _build_prompt(question: str, context: str) -> str:
    return f"""You are a helpful data dictionary assistant for a dbt project.
Answer the question using ONLY the model documentation provided below.
Be concise, precise, and reference specific column names and model names where relevant.
If the answer is not in the context, say so rather than guessing.

=== DBT MODEL DOCUMENTATION ===
{context}
=== END OF DOCUMENTATION ===

Question: {question}

Answer:"""
