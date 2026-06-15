# askdbt

AI-powered data dictionary chatbot for your dbt project — runs **100% locally** via Ollama. No data leaves your organisation.

## What it does

Point `askdbt` at your `manifest.json` and it will:

1. Parse every dbt model and its column-level documentation
2. Embed models as vector chunks using `sentence-transformers`
3. Store them in Qdrant (or pgvector)
4. Answer plain-English questions via a local Ollama LLM

```
You: What does customer_lifetime_value mean?

askdbt: customer_lifetime_value in mart_customer_360 is the predicted net revenue
the bank expects to generate from this customer over the next 36 months. It is
calculated by a gradient boosting CLV model using product holdings, transaction
frequency, fee income, and interest margin as inputs.

Sources: mart_customer_360
```

## Install

```bash
pip install askdbt
```

Requires:
- [Ollama](https://ollama.com) running locally (`ollama pull llama3.2`)
- [Qdrant](https://qdrant.tech) running locally (`docker run -p 6333:6333 qdrant/qdrant`) — or use pgvector

## Quick start

```bash
# 1. Index your dbt project
askdbt index --manifest target/manifest.json

# 2. Chat interactively
askdbt chat

# 3. Or ask a single question
askdbt ask "What is the dpd_bucket column?"

# 4. Launch the Streamlit UI
askdbt ui
```

## Try it with the sample banking manifest

```bash
git clone https://github.com/raghuram36/askdbt
cd askdbt
pip install -e .
askdbt index --manifest sample_data/manifest.json
askdbt chat
```

## Programmatic use

```python
from askdbt import AskDBT

oracle = AskDBT(manifest_path="target/manifest.json")
oracle.index()

answer = oracle.ask("What does customer_lifetime_value mean?")
print(answer)

# Full answer with sources
result = oracle.ask_full("How is fraud rate calculated?")
print(result.answer)
print(result.sources)
```

## Configuration

```python
from askdbt import AskDBT, Config

cfg = Config(
    ollama_model="llama3.2",        # any model pulled via `ollama pull`
    embedding_model="all-MiniLM-L6-v2",
    vector_db="qdrant",             # or "pgvector"
    qdrant_host="localhost",
    qdrant_port=6333,
    top_k=5,
)
oracle = AskDBT("target/manifest.json", config=cfg)
```

### pgvector backend

```bash
pip install "askdbt[pgvector]"
askdbt index --manifest target/manifest.json \
             --vector-db pgvector \
             --pg-dsn postgresql://user:pass@localhost:5432/mydb
```

## Architecture

```
manifest.json
    │
    ▼
ManifestParser          ← parser.py
    │ ModelChunk per model (name, description, columns, tags, …)
    ▼
Indexer                 ← indexer.py
    │ sentence-transformers (all-MiniLM-L6-v2, 384-dim)
    │ upsert into Qdrant or pgvector
    ▼
Retriever               ← retriever.py
    │ embed query → cosine similarity search → top-k chunks
    │ build prompt → Ollama (llama3.2)
    ▼
Answer (text + sources)
```

## CLI reference

```
askdbt index   --manifest PATH [--catalog PATH] [--vector-db qdrant|pgvector]
askdbt ask     QUESTION
askdbt chat
askdbt ui
```

## Why it's safe

- `manifest.json` contains only metadata — model names, descriptions, column names. No actual data rows, no PII.
- Everything runs locally. Ollama never calls an external API.
- Nothing is sent outside your network.

## Development

```bash
pip install -e ".[dev]"
pytest
ruff check src/
mypy src/
```

## License

MIT
