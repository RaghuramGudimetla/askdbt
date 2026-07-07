# askdbt

AI-powered data dictionary chatbot for your dbt project — runs **100% locally** via Ollama.
No data leaves your organisation.

```
You: which columns of dim_customers are not used downstream?

askdbt: ## Column usage analysis for `dim_customers`
        Downstream models analysed: dim_accounts, mart_customer_360, mart_credit_risk
        Unused downstream: `phone_number`, `postcode`
        Used by at least one downstream model: customer_id, full_name, email_address ...
```

---

## Full setup guide

**[docs/getting-started.md](docs/getting-started.md)** — step-by-step instructions for:
- Installing Ollama and pulling a model
- Running Qdrant with Docker
- Installing askdbt
- Generating dbt artifacts (`dbt docs generate`)
- Indexing and chatting

---

## Quick start (if prerequisites are already installed)

```bash
pip install askdbt

# Index your dbt project
askdbt index --manifest target/manifest.json --catalog target/catalog.json

# Chat
askdbt chat
```

Try it immediately with the included sample banking project:

```bash
git clone https://github.com/raghuram36/askdbt
cd askdbt
pip install -e .
askdbt index --manifest sample_data/manifest.json --catalog sample_data/catalog.json
askdbt chat
```

---

## What you can ask

askdbt uses Ollama to classify every question — any phrasing works:

| | Example |
|---|---|
| Count | "how many models?", "total fact tables" |
| List | "show all staging models", "which models are dimensions?" |
| Layer breakdown | "models per layer", "breakdown by layer" |
| Dependencies | "show the dependency tree" |
| Column usage | "which columns of dim_customers aren't used downstream?" |
| **Impact analysis** | "what breaks if I remove credit_score from dim_customers?" |
| **Upstream lineage** | "where does customer_id come from in mart_customer_360?" |
| **Column trace** | "trace credit_limit from source to mart" |
| Describe | "what does mart_credit_risk do?" |
| SQL | "show the SQL for fct_transactions" |
| Size | "how big is fct_transactions?", "which models have over 1M rows?" |

---

## CLI reference

```
askdbt index   --manifest PATH [--catalog PATH] [--recreate] [--vector-db qdrant|pgvector]
askdbt ask     "QUESTION"
askdbt chat
askdbt ui
```

---

## Architecture

```
manifest.json + catalog.json
        │
        ▼
  ManifestParser  →  ModelChunk (SQL, columns, deps, child_ids, stats)
        │
        ▼
    Indexer  →  sentence-transformers (384-dim)  →  Qdrant / pgvector
        │
        ▼
  Retriever
        ├── Ollama classifies intent (count / list / deps / column_usage /
        │                            impact_analysis / upstream_lineage / column_trace / general)
        ├── Meta questions  →  answered directly from vector store (exact, no hallucination)
        │     column_usage      : sqlglot AST parse of compiled SQL per downstream model
        │     impact_analysis   : transitive DAG walk + sqlglot column reference check
        │     upstream_lineage  : BFS upward through depends_on, traces column origin
        │     column_trace      : bidirectional — upstream origin + downstream impact
        └── General questions  →  cosine search → top-k chunks → Ollama answer
```

---

## Why it's safe

- `manifest.json` contains only metadata — model names, descriptions, SQL, column names. No actual data rows, no PII from your warehouse.
- Everything runs locally. Ollama never calls an external API.
- Nothing is sent outside your network.

---

## Development

```bash
git clone https://github.com/raghuram36/askdbt
cd askdbt
pip install -e ".[dev]"
pytest
ruff check src/
mypy src/
```

---

## License

MIT
