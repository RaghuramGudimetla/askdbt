from dataclasses import dataclass, field
from typing import Literal


@dataclass
class Config:
    # LLM
    ollama_base_url: str = "http://localhost:11434"
    ollama_model: str = "llama3.2"

    # Embeddings
    embedding_model: str = "all-MiniLM-L6-v2"
    embedding_dim: int = 384

    # Vector DB
    vector_db: Literal["qdrant", "pgvector"] = "qdrant"

    # Qdrant
    qdrant_host: str = "localhost"
    qdrant_port: int = 6333
    qdrant_collection: str = "askdbt"

    # pgvector
    pg_dsn: str = "postgresql://localhost:5432/askdbt"
    pg_table: str = "dbt_embeddings"

    # RAG
    top_k: int = 5
    score_threshold: float = 0.3


_default = Config()


def get_config() -> Config:
    return _default
