"""Click CLI — askdbt index / askdbt chat / askdbt ask."""

from __future__ import annotations

import sys
from pathlib import Path

import click

from .config import Config
from .indexer import Indexer
from .parser import ManifestParser
from .retriever import Retriever


def _make_config(**overrides) -> Config:
    cfg = Config()
    for k, v in overrides.items():
        if v is not None:
            setattr(cfg, k, v)
    return cfg


@click.group()
@click.version_option()
def cli():
    """askdbt — AI-powered data dictionary for your dbt project."""


@cli.command()
@click.option("--manifest", "-m", required=True, type=click.Path(exists=True), help="Path to manifest.json")
@click.option("--catalog", "-c", default=None, type=click.Path(), help="Path to catalog.json (optional)")
@click.option("--vector-db", default="qdrant", type=click.Choice(["qdrant", "pgvector"]), show_default=True)
@click.option("--qdrant-host", default="localhost", show_default=True)
@click.option("--qdrant-port", default=6333, show_default=True)
@click.option("--qdrant-collection", default="askdbt", show_default=True)
@click.option("--pg-dsn", default=None, help="PostgreSQL DSN for pgvector backend")
@click.option("--embedding-model", default="all-MiniLM-L6-v2", show_default=True)
@click.option("--ollama-model", default="llama3.2", show_default=True)
def index(manifest, catalog, vector_db, qdrant_host, qdrant_port, qdrant_collection, pg_dsn, embedding_model, ollama_model):
    """Parse manifest.json and index all models into the vector store."""
    click.echo(f"Parsing {manifest} ...")
    parser = ManifestParser(manifest, catalog)
    chunks = parser.parse()
    click.echo(f"  Found {len(chunks)} models.")

    cfg = _make_config(
        vector_db=vector_db,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        qdrant_collection=qdrant_collection,
        pg_dsn=pg_dsn,
        embedding_model=embedding_model,
        ollama_model=ollama_model,
    )

    indexer = Indexer(cfg)
    n = indexer.index(chunks)
    click.secho(f"  Indexed {n} models into {vector_db}.", fg="green")


@cli.command()
@click.argument("question")
@click.option("--manifest", "-m", default=None, type=click.Path(exists=True))
@click.option("--vector-db", default="qdrant", type=click.Choice(["qdrant", "pgvector"]))
@click.option("--qdrant-host", default="localhost")
@click.option("--qdrant-port", default=6333)
@click.option("--qdrant-collection", default="askdbt")
@click.option("--pg-dsn", default=None)
@click.option("--ollama-model", default="llama3.2", show_default=True)
@click.option("--ollama-url", default="http://localhost:11434", show_default=True)
@click.option("--top-k", default=5, show_default=True)
def ask(question, manifest, vector_db, qdrant_host, qdrant_port, qdrant_collection, pg_dsn, ollama_model, ollama_url, top_k):
    """Ask a single question and print the answer."""
    cfg = _make_config(
        vector_db=vector_db,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        qdrant_collection=qdrant_collection,
        pg_dsn=pg_dsn,
        ollama_model=ollama_model,
        ollama_base_url=ollama_url,
        top_k=top_k,
    )
    retriever = Retriever(cfg)
    result = retriever.ask(question)

    click.echo("")
    click.secho("Answer:", bold=True)
    click.echo(result.answer)
    if result.sources:
        click.echo("")
        click.secho("Sources: " + ", ".join(result.sources), dim=True)


@cli.command()
@click.option("--vector-db", default="qdrant", type=click.Choice(["qdrant", "pgvector"]))
@click.option("--qdrant-host", default="localhost")
@click.option("--qdrant-port", default=6333)
@click.option("--qdrant-collection", default="askdbt")
@click.option("--pg-dsn", default=None)
@click.option("--ollama-model", default="llama3.2", show_default=True)
@click.option("--ollama-url", default="http://localhost:11434", show_default=True)
@click.option("--top-k", default=5, show_default=True)
def chat(vector_db, qdrant_host, qdrant_port, qdrant_collection, pg_dsn, ollama_model, ollama_url, top_k):
    """Start an interactive REPL chat session."""
    cfg = _make_config(
        vector_db=vector_db,
        qdrant_host=qdrant_host,
        qdrant_port=qdrant_port,
        qdrant_collection=qdrant_collection,
        pg_dsn=pg_dsn,
        ollama_model=ollama_model,
        ollama_base_url=ollama_url,
        top_k=top_k,
    )
    retriever = Retriever(cfg)

    click.secho("askdbt chat — type 'quit' or Ctrl-C to exit.\n", bold=True)
    while True:
        try:
            question = click.prompt(click.style("You", fg="cyan", bold=True))
        except (EOFError, KeyboardInterrupt):
            click.echo("\nBye!")
            sys.exit(0)

        if question.strip().lower() in {"quit", "exit", "q"}:
            click.echo("Bye!")
            break

        result = retriever.ask(question)
        click.echo("")
        click.secho("askdbt: ", fg="green", bold=True, nl=False)
        click.echo(result.answer)
        if result.sources:
            click.secho("  [sources: " + ", ".join(result.sources) + "]", dim=True)
        click.echo("")


@cli.command()
@click.option("--vector-db", default="qdrant", type=click.Choice(["qdrant", "pgvector"]))
@click.option("--qdrant-host", default="localhost")
@click.option("--qdrant-port", default=6333)
@click.option("--qdrant-collection", default="askdbt")
@click.option("--pg-dsn", default=None)
@click.option("--ollama-model", default="llama3.2", show_default=True)
@click.option("--ollama-url", default="http://localhost:11434", show_default=True)
def ui(vector_db, qdrant_host, qdrant_port, qdrant_collection, pg_dsn, ollama_model, ollama_url):
    """Launch the Streamlit chat UI."""
    import subprocess

    chat_module = Path(__file__).parent / "chat.py"
    env_vars = (
        f"ASKDBT_VECTOR_DB={vector_db} "
        f"ASKDBT_QDRANT_HOST={qdrant_host} "
        f"ASKDBT_QDRANT_PORT={qdrant_port} "
        f"ASKDBT_QDRANT_COLLECTION={qdrant_collection} "
        f"ASKDBT_OLLAMA_MODEL={ollama_model} "
        f"ASKDBT_OLLAMA_URL={ollama_url} "
    )
    click.echo("Launching Streamlit UI...")
    subprocess.run(f"{env_vars}streamlit run {chat_module}", shell=True)
