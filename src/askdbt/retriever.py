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

    def _classify_intent(self, question: str) -> dict:
        """Ask Ollama to classify the question intent. Returns a dict with 'intent' and optional 'layer'."""
        prompt = """\
You are a dbt question classifier. Classify the user's question into exactly one intent.
Return ONLY a raw JSON object — no markdown, no explanation, no extra text.

Fields:
- "intent": one of: count_all, count_layer, list_all, list_layer, layer_breakdown, dependencies, column_usage, general
- "layer": (only when intent is count_layer or list_layer) one of: staging, dim, fact, intermediate, mart
- "model_name": (only when intent is column_usage) the dbt model name the question is about

Intent definitions:
- count_all        : total count of all models in the project
- count_layer      : count of models in one specific dbt layer
- list_all         : list / show all model names
- list_layer       : list / show model names in one specific layer
- layer_breakdown  : counts or listing grouped by every layer
- dependencies     : model dependencies, lineage, upstream, downstream, DAG
- column_usage     : which columns of a specific model are / are not used by downstream models
- general          : anything else — describe a model, show SQL, owners, tags, etc.

Examples:
"how many models?" → {"intent": "count_all"}
"total mart models" → {"intent": "count_layer", "layer": "mart"}
"give me a count of fact tables" → {"intent": "count_layer", "layer": "fact"}
"show me all staging models" → {"intent": "list_layer", "layer": "staging"}
"which models are dimensions?" → {"intent": "list_layer", "layer": "dim"}
"models per layer" → {"intent": "layer_breakdown"}
"how many models in each layer?" → {"intent": "layer_breakdown"}
"show the full dependency tree" → {"intent": "dependencies"}
"which columns of dim_customers are not used downstream?" → {"intent": "column_usage", "model_name": "dim_customers"}
"what columns from fct_transactions go unused?" → {"intent": "column_usage", "model_name": "fct_transactions"}
"are all columns in stg_accounts consumed by downstream models?" → {"intent": "column_usage", "model_name": "stg_accounts"}
"what does dim_customers do?" → {"intent": "general"}
"show SQL for mart_credit_risk" → {"intent": "general"}

Question: """ + question

        url = f"{self.config.ollama_base_url}/api/generate"
        try:
            resp = requests.post(
                url,
                json={"model": self.config.ollama_model, "prompt": prompt,
                      "stream": False, "format": "json"},
                timeout=30,
            )
            resp.raise_for_status()
            raw = resp.json().get("response", "{}")
            return json.loads(raw)
        except Exception:
            return {"intent": "general"}

    def _try_meta_answer(self, question: str) -> str | None:
        """Classify the question with Ollama and answer directly from the vector store if it's a meta question."""
        classification = self._classify_intent(question)
        intent = classification.get("intent", "general")
        layer  = classification.get("layer")

        _layer_prefix = {
            "staging": "stg_", "stg": "stg_",
            "dim": "dim_", "dimension": "dim_",
            "fact": "fct_", "fct": "fct_",
            "intermediate": "int_", "int": "int_",
            "mart": "mart_",
        }
        layer_filter = _layer_prefix.get(layer) if layer else None

        if intent == "general":
            return None

        is_qdrant   = self.config.vector_db == "qdrant"
        is_pgvector = self.config.vector_db == "pgvector"

        if intent == "layer_breakdown":
            return self._meta_layer_breakdown_qdrant() if is_qdrant else self._meta_layer_breakdown_pgvector()

        if intent == "dependencies":
            return (self._meta_qdrant(count_only=False, deps_only=True)
                    if is_qdrant else
                    self._meta_pgvector(count_only=False, deps_only=True))

        if intent == "count_all":
            return (self._meta_qdrant(count_only=True, deps_only=False)
                    if is_qdrant else
                    self._meta_pgvector(count_only=True, deps_only=False))

        if intent == "count_layer":
            return (self._meta_qdrant(count_only=True, deps_only=False, layer_filter=layer_filter)
                    if is_qdrant else
                    self._meta_pgvector(count_only=True, deps_only=False, layer_filter=layer_filter))

        if intent in ("list_all", "list_layer"):
            lf = layer_filter if intent == "list_layer" else None
            return (self._meta_qdrant(count_only=False, deps_only=False, layer_filter=lf)
                    if is_qdrant else
                    self._meta_pgvector(count_only=False, deps_only=False, layer_filter=lf))

        if intent == "column_usage":
            model_name = classification.get("model_name", "")
            if not model_name:
                return None
            return (self._meta_column_usage_qdrant(model_name)
                    if is_qdrant else
                    self._meta_column_usage_pgvector(model_name))

        return None

    def _meta_qdrant(self, count_only: bool, deps_only: bool, layer_filter: str | None = None) -> str:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=self.config.qdrant_host, port=self.config.qdrant_port)
        total_all = client.count(collection_name=self.config.qdrant_collection).count

        results, _ = client.scroll(
            collection_name=self.config.qdrant_collection,
            limit=total_all,
            with_payload=True,
        )

        if layer_filter:
            results = [r for r in results if r.payload.get("model_name", "").startswith(layer_filter)]

        total = len(results)
        _layer_labels = {"stg_": "staging", "dim_": "dimension", "fct_": "fact",
                         "int_": "intermediate", "mart_": "mart"}
        label = f"{_layer_labels.get(layer_filter, layer_filter.rstrip('_'))} models" if layer_filter else "models"

        if deps_only:
            return _format_dependencies(results)

        names = sorted(r.payload.get("model_name", "") for r in results)

        if count_only and not layer_filter:
            return f"There are **{total} {label}** indexed in this dbt project."

        bullet_list = "\n".join(f"- {n}" for n in names)
        return f"There are **{total} {label}** in this dbt project:\n\n{bullet_list}"

    def _meta_pgvector(self, count_only: bool, deps_only: bool, layer_filter: str | None = None) -> str:
        import psycopg2

        conn = psycopg2.connect(self.config.pg_dsn)
        cur = conn.cursor()
        cur.execute(f"SELECT model_name, text FROM {self.config.pg_table} ORDER BY model_name")
        rows = cur.fetchall()
        cur.close()
        conn.close()

        if layer_filter:
            rows = [r for r in rows if r[0].startswith(layer_filter)]

        total = len(rows)
        _layer_labels = {"stg_": "staging", "dim_": "dimension", "fct_": "fact",
                         "int_": "intermediate", "mart_": "mart"}
        label = f"{_layer_labels.get(layer_filter, layer_filter.rstrip('_'))} models" if layer_filter else "models"

        if deps_only:
            records = [type("R", (), {"payload": {"model_name": r[0], "text": r[1]}})() for r in rows]
            return _format_dependencies(records)

        names = [r[0] for r in rows]

        if count_only and not layer_filter:
            return f"There are **{total} {label}** indexed in this dbt project."

        bullet_list = "\n".join(f"- {n}" for n in names)
        return f"There are **{total} {label}** in this dbt project:\n\n{bullet_list}"

    def _meta_column_usage_qdrant(self, model_name: str) -> str:
        from qdrant_client import QdrantClient
        from qdrant_client.models import FieldCondition, Filter, MatchValue

        client = QdrantClient(host=self.config.qdrant_host, port=self.config.qdrant_port)
        total = client.count(collection_name=self.config.qdrant_collection).count

        # Fetch all points (small collection — max hundreds of models)
        all_points, _ = client.scroll(
            collection_name=self.config.qdrant_collection,
            limit=total,
            with_payload=True,
        )
        by_id   = {p.payload.get("model_id", ""): p.payload for p in all_points}
        by_name = {p.payload.get("model_name", ""): p.payload for p in all_points}

        upstream = by_name.get(model_name)
        if not upstream:
            return f"Model **{model_name}** not found in the index."

        return _analyse_column_usage(model_name, upstream, by_id)

    def _meta_column_usage_pgvector(self, model_name: str) -> str:
        import psycopg2

        conn = psycopg2.connect(self.config.pg_dsn)
        cur = conn.cursor()
        cur.execute(
            f"SELECT model_id, model_name, column_names, child_ids, compiled_sql "
            f"FROM {self.config.pg_table}"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        by_id   = {r[0]: {"model_id": r[0], "model_name": r[1], "column_names": r[2],
                           "child_ids": r[3], "compiled_sql": r[4]} for r in rows}
        by_name = {v["model_name"]: v for v in by_id.values()}

        upstream = by_name.get(model_name)
        if not upstream:
            return f"Model **{model_name}** not found in the index."

        return _analyse_column_usage(model_name, upstream, by_id)

    def _meta_layer_breakdown_qdrant(self) -> str:
        from qdrant_client import QdrantClient

        client = QdrantClient(host=self.config.qdrant_host, port=self.config.qdrant_port)
        total = client.count(collection_name=self.config.qdrant_collection).count
        results, _ = client.scroll(
            collection_name=self.config.qdrant_collection,
            limit=total,
            with_payload=True,
        )
        names = [r.payload.get("model_name", "") for r in results]
        return _format_layer_breakdown(names)

    def _meta_layer_breakdown_pgvector(self) -> str:
        import psycopg2

        conn = psycopg2.connect(self.config.pg_dsn)
        cur = conn.cursor()
        cur.execute(f"SELECT model_name FROM {self.config.pg_table}")
        names = [r[0] for r in cur.fetchall()]
        cur.close()
        conn.close()
        return _format_layer_breakdown(names)

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


def _analyse_column_usage(model_name: str, upstream_payload: dict, all_payloads_by_id: dict) -> str:
    """Cross-reference upstream column list against every downstream model's compiled SQL."""
    column_names: list[str] = upstream_payload.get("column_names", [])
    child_ids:    list[str] = upstream_payload.get("child_ids", [])

    if not column_names:
        return f"No column information is available for **{model_name}** in the index."

    if not child_ids:
        return (
            f"**{model_name}** has no downstream models — it is a leaf node.\n\n"
            f"Columns ({len(column_names)}): {', '.join(sorted(column_names))}"
        )

    # For each child, parse its compiled SQL and find which columns are referenced
    usage: dict[str, set[str]] = {}   # child_name → set of upstream cols it uses
    missing_sql: list[str] = []

    for child_id in child_ids:
        child = all_payloads_by_id.get(child_id)
        if not child:
            continue
        child_name = child.get("model_name", child_id)
        compiled   = child.get("compiled_sql", "")
        if not compiled:
            missing_sql.append(child_name)
            continue
        usage[child_name] = _columns_used_from_upstream(compiled, column_names)

    # Union of all columns used by any downstream model
    all_used   = set().union(*usage.values()) if usage else set()
    unused     = sorted(c for c in column_names if c.lower() not in {u.lower() for u in all_used})
    used_cols  = sorted(all_used)

    lines = [f"## Column usage analysis for `{model_name}`\n"]
    lines.append(f"**Downstream models analysed:** {', '.join(sorted(usage))}")
    if missing_sql:
        lines.append(f"**Skipped (no compiled SQL):** {', '.join(missing_sql)}")

    lines.append("")
    if unused:
        lines.append(f"### Unused downstream ({len(unused)} columns)")
        lines.extend(f"- `{c}`" for c in unused)
    else:
        lines.append("### All columns are used by at least one downstream model ✓")

    lines.append(f"\n### Used by at least one downstream model ({len(used_cols)} columns)")
    lines.extend(f"- `{c}`" for c in used_cols)

    lines.append("\n### Per-model breakdown")
    for child_name, cols in sorted(usage.items()):
        lines.append(f"**{child_name}** uses: {', '.join(f'`{c}`' for c in sorted(cols)) or '—'}")

    return "\n".join(lines)


def _columns_used_from_upstream(compiled_sql: str, upstream_cols: list[str], dialect: str = "postgres") -> set[str]:
    """Parse compiled SQL with sqlglot and return which upstream column names are referenced."""
    import sqlglot

    upstream_lower = {c.lower() for c in upstream_cols}
    if not compiled_sql.strip():
        return upstream_lower  # no SQL → conservative: assume all used

    try:
        tree = sqlglot.parse_one(compiled_sql, dialect=dialect)
    except Exception:
        return upstream_lower  # unparseable → conservative

    # Collect every explicitly named column reference in the AST
    referenced = {n.name.lower() for n in tree.walk() if isinstance(n, sqlglot.exp.Column)}
    used = upstream_lower & referenced

    # If the outermost SELECT itself is SELECT *, assume all upstream cols flow through
    outer_select = tree.find(sqlglot.exp.Select)
    if outer_select and any(isinstance(e, sqlglot.exp.Star) for e in outer_select.expressions):
        return upstream_lower

    return used


def _format_layer_breakdown(model_names: list[str]) -> str:
    layers = [
        ("Staging",      "stg_"),
        ("Dimensions",   "dim_"),
        ("Facts",        "fct_"),
        ("Intermediate", "int_"),
        ("Marts",        "mart_"),
    ]
    lines = ["**Models by layer:**\n"]
    total = 0
    for label, prefix in layers:
        matches = sorted(n for n in model_names if n.startswith(prefix))
        if matches:
            lines.append(f"**{label}** ({len(matches)})")
            lines.extend(f"  - {n}" for n in matches)
            total += len(matches)
    other = sorted(n for n in model_names if not any(n.startswith(p) for _, p in layers))
    if other:
        lines.append(f"**Other** ({len(other)})")
        lines.extend(f"  - {n}" for n in other)
        total += len(other)
    lines.append(f"\n**Total: {total} models**")
    return "\n".join(lines)


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
