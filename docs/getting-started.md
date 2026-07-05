# Getting Started with askdbt

askdbt turns your dbt project's `manifest.json` into a local AI-powered data dictionary.
Ask plain-English questions — it answers using your own documentation, entirely on your machine.
No data leaves your organisation.

---

## Prerequisites

| Tool | Minimum version | Purpose |
|---|---|---|
| Python | 3.11 | askdbt runtime |
| Docker | any recent version | Run Qdrant vector database |
| Ollama | latest | Run the local LLM |
| dbt Core | 1.5+ | Generate `manifest.json` and `catalog.json` |

---

## Step 1 — Install Ollama

Ollama runs the language model completely locally.

### macOS

```bash
brew install ollama
```

Or download the macOS app from [ollama.com/download](https://ollama.com/download) and drag it to Applications.

### Linux

```bash
curl -fsSL https://ollama.com/install.sh | sh
```

### Windows

Download the installer from [ollama.com/download](https://ollama.com/download) and run it.

---

### Start the Ollama server

```bash
ollama serve
```

Leave this running in a terminal. On macOS, if you installed the app it starts automatically in the menu bar.

---

### Pull the language model

```bash
ollama pull llama3.2
```

This downloads ~2 GB once and caches it locally. You can use any Ollama-compatible model:

```bash
ollama pull mistral        # lighter, faster
ollama pull llama3.1:8b   # more capable
ollama pull phi3           # smallest footprint
```

Verify Ollama is ready:

```bash
curl http://localhost:11434/api/tags
# Should return a JSON list of your downloaded models
```

---

## Step 2 — Run Qdrant

Qdrant is the vector database that stores your embedded dbt models.

### Using Docker (recommended)

```bash
docker run -d \
  --name qdrant \
  -p 6333:6333 \
  -v $(pwd)/qdrant_storage:/qdrant/storage \
  qdrant/qdrant
```

- `-d` runs it in the background
- `-v` persists your index to disk so you don't need to re-index after a restart
- Port `6333` is the default — don't change it unless you pass `--qdrant-port` to askdbt

Verify Qdrant is running:

```bash
curl http://localhost:6333/healthz
# Should return: healthz check passed
```

### Check if Qdrant is already running

```bash
docker ps | grep qdrant
```

If it's already running, don't start a second instance — just proceed to Step 3.

### Stop / restart Qdrant

```bash
docker stop qdrant
docker start qdrant
```

---

## Step 3 — Install askdbt

```bash
pip install askdbt
```

With pgvector support (optional alternative to Qdrant):

```bash
pip install "askdbt[pgvector]"
```

Verify the install:

```bash
askdbt --version
```

---

## Step 4 — Generate dbt artifacts

In your dbt project directory, run:

```bash
dbt docs generate
```

This produces two files in the `target/` folder:

| File | What it contains |
|---|---|
| `target/manifest.json` | Every model: SQL, columns, descriptions, dependencies, tags |
| `target/catalog.json` | Warehouse metadata: actual column types, row counts, table sizes |

Both files are used by askdbt. `catalog.json` is optional but strongly recommended — it adds row counts and actual data types to the answers.

---

## Step 5 — Index your dbt project

```bash
askdbt index \
  --manifest target/manifest.json \
  --catalog  target/catalog.json
```

This embeds every model into Qdrant. You only need to re-run this when your dbt project changes.

### Options

```
--manifest PATH       Path to manifest.json (required)
--catalog  PATH       Path to catalog.json  (optional, adds row counts)
--recreate            Drop and rebuild the collection from scratch
--vector-db           qdrant (default) or pgvector
--qdrant-host         default: localhost
--qdrant-port         default: 6333
--qdrant-collection   default: askdbt
--embedding-model     default: all-MiniLM-L6-v2
--ollama-model        default: llama3.2
```

Example with a custom collection name:

```bash
askdbt index \
  --manifest target/manifest.json \
  --catalog  target/catalog.json \
  --qdrant-collection my_project \
  --recreate
```

---

## Step 6 — Ask questions

### Interactive chat (recommended)

```bash
askdbt chat
```

```
askdbt chat — type 'quit' or Ctrl-C to exit.

You: what does mart_customer_360 do?
askdbt: mart_customer_360 is a 360-degree customer summary mart...

You: which columns of dim_customers are not used downstream?
askdbt: ## Column usage analysis for `dim_customers`
        Downstream models analysed: dim_accounts, mart_customer_360...

You: how many models are there?
askdbt: There are 18 models indexed in this dbt project.

You: quit
```

### Single question

```bash
askdbt ask "what is the ecl_provision column?"
```

### Streamlit UI

```bash
askdbt ui
```

Opens a browser-based chat interface at `http://localhost:8501`.

---

## Question types askdbt understands

askdbt uses Ollama to classify every question before answering, so any natural phrasing works.

| Category | Example questions |
|---|---|
| Count models | "how many models do we have?", "total fact tables", "give me a count of staging models" |
| List models | "show me all mart models", "which models are dimensions?", "list staging tables" |
| Layer breakdown | "models per layer", "breakdown by layer", "how many models in each layer?" |
| Dependencies | "show the dependency tree", "what upstream models does mart_credit_risk use?" |
| Column usage | "which columns of dim_customers aren't used downstream?", "what columns from fct_transactions go unused?" |
| Describe a model | "what does int_loan_arrears do?", "explain mart_fraud_summary" |
| Column meaning | "what is the ifrs9_stage column?", "what does ecl_provision mean?" |
| SQL | "show the SQL for mart_credit_risk" |
| Size / stats | "how big is fct_transactions?", "which models have more than 1 million rows?" |

---

## Try it with the sample banking project

The repo includes a complete sample dbt project (18 banking models: staging → dimensions → facts → intermediates → marts) so you can try askdbt without needing your own dbt project.

```bash
git clone https://github.com/raghuram36/askdbt
cd askdbt
pip install -e .

askdbt index \
  --manifest sample_data/manifest.json \
  --catalog  sample_data/catalog.json

askdbt chat
```

---

## Troubleshooting

### `Could not connect to Ollama`

```
Could not connect to Ollama at http://localhost:11434. Make sure Ollama is running: `ollama serve`
```

Start Ollama:
```bash
ollama serve          # Linux / macOS terminal
# or open the Ollama app on macOS
```

---

### `port is already allocated` when starting Qdrant

Qdrant is already running. Check:
```bash
docker ps | grep qdrant
```
If it is running, skip `docker run` — just proceed.

---

### `numpy.dtype size changed` error

Numpy 2.x breaks binary compatibility with some packages. Fix:
```bash
pip install "numpy<2.0"
```

---

### Re-index after dbt project changes

Whenever you run `dbt docs generate` with new or changed models, re-index:

```bash
askdbt index \
  --manifest target/manifest.json \
  --catalog  target/catalog.json \
  --recreate
```

The `--recreate` flag drops the old collection and rebuilds it cleanly.

---

### Qdrant data persists between restarts

If you mounted a volume (`-v $(pwd)/qdrant_storage:/qdrant/storage`), your index survives a Docker restart. If you didn't, you'll need to re-index after restarting the container.

---

## pgvector alternative

If you prefer PostgreSQL over Qdrant:

```bash
# Start PostgreSQL with pgvector
docker run -d \
  --name pgvector \
  -e POSTGRES_PASSWORD=password \
  -p 5432:5432 \
  pgvector/pgvector:pg16

# Install askdbt with pgvector support
pip install "askdbt[pgvector]"

# Index
askdbt index \
  --manifest target/manifest.json \
  --vector-db pgvector \
  --pg-dsn "postgresql://postgres:password@localhost:5432/postgres"

# Chat
askdbt chat \
  --vector-db pgvector \
  --pg-dsn "postgresql://postgres:password@localhost:5432/postgres"
```

---

## Architecture overview

```
dbt project
    │
    ├── target/manifest.json   ← model SQL, descriptions, columns, dependencies
    └── target/catalog.json    ← warehouse stats (row counts, types, sizes)
              │
              ▼
        ManifestParser                         parser.py
              │  ModelChunk per model
              ▼
           Indexer                             indexer.py
              │  sentence-transformers (all-MiniLM-L6-v2, 384-dim)
              │  upsert into Qdrant / pgvector
              ▼
         Retriever                             retriever.py
              │
              ├── Ollama classifies intent
              │     count / list / breakdown / dependencies / column_usage / general
              │
              ├── Meta questions ──► answered directly from vector store
              │                      (exact, no hallucination)
              │
              └── General questions ──► cosine search → top-k chunks
                                        ──► Ollama generates answer
                                              │
                                              ▼
                                        Answer + sources
```

Everything runs on your machine. No cloud calls. No telemetry.
