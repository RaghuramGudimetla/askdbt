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
        """Ask Ollama to classify the question intent. Returns a dict with 'intent' and optional fields."""
        prompt = """\
You are a dbt question classifier. Classify the user's question into exactly one intent.
Return ONLY a raw JSON object — no markdown, no explanation, no extra text.

Fields:
- "intent": one of: count_all, count_layer, list_all, list_layer, layer_breakdown, dependencies,
             column_usage, impact_analysis, upstream_lineage, column_trace, general
- "layer": (only when intent is count_layer or list_layer) one of: staging, dim, fact, intermediate, mart
- "model_name": (required for column_usage, impact_analysis, upstream_lineage, column_trace) the dbt model name
- "column_name": (required for impact_analysis, upstream_lineage, column_trace) the specific column name

Intent definitions:
- count_all         : total count of all models in the project
- count_layer       : count of models in one specific dbt layer
- list_all          : list / show all model names
- list_layer        : list / show model names in one specific layer
- layer_breakdown   : counts or listing grouped by every layer
- dependencies      : model dependencies, lineage, upstream, downstream, DAG
- column_usage      : which columns of a specific model are / are not used by downstream models
- impact_analysis   : what breaks / is affected if a specific column is removed or changed in a model
- upstream_lineage  : where a specific column originates — which upstream model first computes or defines it
- column_trace      : full end-to-end lineage of a column — both where it comes from and where it flows to
- general           : anything else — describe a model, show SQL, owners, tags, column meaning, etc.

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
"what breaks if I remove credit_score from dim_customers?" → {"intent": "impact_analysis", "model_name": "dim_customers", "column_name": "credit_score"}
"which downstream models use the ecl_provision column in mart_credit_risk?" → {"intent": "impact_analysis", "model_name": "mart_credit_risk", "column_name": "ecl_provision"}
"if I change risk_score in dim_customers what would break?" → {"intent": "impact_analysis", "model_name": "dim_customers", "column_name": "risk_score"}
"where does customer_id come from in mart_customer_360?" → {"intent": "upstream_lineage", "model_name": "mart_customer_360", "column_name": "customer_id"}
"which model computes ecl_provision?" → {"intent": "upstream_lineage", "model_name": "mart_credit_risk", "column_name": "ecl_provision"}
"trace the origin of account_balance in dim_accounts" → {"intent": "upstream_lineage", "model_name": "dim_accounts", "column_name": "account_balance"}
"trace customer_id from source to mart" → {"intent": "column_trace", "model_name": "mart_customer_360", "column_name": "customer_id"}
"show full lineage of credit_limit through dim_accounts" → {"intent": "column_trace", "model_name": "dim_accounts", "column_name": "credit_limit"}
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

        if intent == "impact_analysis":
            model_name  = classification.get("model_name", "")
            column_name = classification.get("column_name", "")
            if not model_name or not column_name:
                return None
            return (self._meta_impact_qdrant(model_name, column_name)
                    if is_qdrant else
                    self._meta_impact_pgvector(model_name, column_name))

        if intent == "upstream_lineage":
            model_name  = classification.get("model_name", "")
            column_name = classification.get("column_name", "")
            if not model_name or not column_name:
                return None
            return (self._meta_upstream_qdrant(model_name, column_name)
                    if is_qdrant else
                    self._meta_upstream_pgvector(model_name, column_name))

        if intent == "column_trace":
            model_name  = classification.get("model_name", "")
            column_name = classification.get("column_name", "")
            if not model_name or not column_name:
                return None
            return (self._meta_column_trace_qdrant(model_name, column_name)
                    if is_qdrant else
                    self._meta_column_trace_pgvector(model_name, column_name))

        return None

    # ------------------------------------------------------------------ #
    # Shared fetch helper                                                   #
    # ------------------------------------------------------------------ #

    def _fetch_all_payloads_qdrant(self) -> tuple[dict, dict]:
        """Return (by_id, by_name) payload dicts from the full Qdrant collection."""
        from qdrant_client import QdrantClient

        client = QdrantClient(host=self.config.qdrant_host, port=self.config.qdrant_port)
        total = client.count(collection_name=self.config.qdrant_collection).count
        points, _ = client.scroll(
            collection_name=self.config.qdrant_collection,
            limit=total,
            with_payload=True,
        )
        by_id   = {p.payload.get("model_id", ""): p.payload for p in points}
        by_name = {p.payload.get("model_name", ""): p.payload for p in points}
        return by_id, by_name

    def _fetch_all_payloads_pgvector(self) -> tuple[dict, dict]:
        import psycopg2

        conn = psycopg2.connect(self.config.pg_dsn)
        cur = conn.cursor()
        cur.execute(
            f"SELECT model_id, model_name, text, depends_on, child_ids, "
            f"all_downstream_ids, column_names, compiled_sql "
            f"FROM {self.config.pg_table}"
        )
        rows = cur.fetchall()
        cur.close()
        conn.close()

        by_id: dict = {}
        by_name: dict = {}
        for r in rows:
            p = {
                "model_id": r[0], "model_name": r[1], "text": r[2],
                "depends_on": r[3] or [], "child_ids": r[4] or [],
                "all_downstream_ids": r[5] or [], "column_names": r[6] or [],
                "compiled_sql": r[7] or "",
            }
            by_id[r[0]]   = p
            by_name[r[1]] = p
        return by_id, by_name

    # ------------------------------------------------------------------ #
    # Existing meta handlers                                               #
    # ------------------------------------------------------------------ #

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
        by_id, by_name = self._fetch_all_payloads_qdrant()
        upstream = by_name.get(model_name)
        if not upstream:
            return f"Model **{model_name}** not found in the index."
        return _analyse_column_usage(model_name, upstream, by_id)

    def _meta_column_usage_pgvector(self, model_name: str) -> str:
        by_id, by_name = self._fetch_all_payloads_pgvector()
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

    # ------------------------------------------------------------------ #
    # New lineage handlers                                                  #
    # ------------------------------------------------------------------ #

    def _meta_impact_qdrant(self, model_name: str, column_name: str) -> str:
        by_id, by_name = self._fetch_all_payloads_qdrant()
        return _analyse_impact(model_name, column_name, by_name, by_id)

    def _meta_impact_pgvector(self, model_name: str, column_name: str) -> str:
        by_id, by_name = self._fetch_all_payloads_pgvector()
        return _analyse_impact(model_name, column_name, by_name, by_id)

    def _meta_upstream_qdrant(self, model_name: str, column_name: str) -> str:
        by_id, by_name = self._fetch_all_payloads_qdrant()
        return _analyse_upstream_lineage(model_name, column_name, by_name)

    def _meta_upstream_pgvector(self, model_name: str, column_name: str) -> str:
        by_id, by_name = self._fetch_all_payloads_pgvector()
        return _analyse_upstream_lineage(model_name, column_name, by_name)

    def _meta_column_trace_qdrant(self, model_name: str, column_name: str) -> str:
        by_id, by_name = self._fetch_all_payloads_qdrant()
        return _analyse_column_trace(model_name, column_name, by_name, by_id)

    def _meta_column_trace_pgvector(self, model_name: str, column_name: str) -> str:
        by_id, by_name = self._fetch_all_payloads_pgvector()
        return _analyse_column_trace(model_name, column_name, by_name, by_id)

    # ------------------------------------------------------------------ #
    # Ollama                                                               #
    # ------------------------------------------------------------------ #

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


# ====================================================================== #
# Module-level analysis functions (pure — receive data, return Markdown)  #
# ====================================================================== #

def _layer_of(model_name: str) -> str:
    for prefix, label in [("stg_", "staging"), ("dim_", "dimension"), ("fct_", "fact"),
                           ("int_", "intermediate"), ("mart_", "mart")]:
        if model_name.startswith(prefix):
            return label
    return "model"


def _analyse_impact(
    model_name: str,
    column_name: str,
    by_name: dict,
    by_id: dict,
) -> str:
    """Find every downstream model that directly references column_name in its SQL."""
    upstream = by_name.get(model_name)
    if not upstream:
        return f"Model **{model_name}** not found in the index."

    col_names = upstream.get("column_names", [])
    if column_name.lower() not in {c.lower() for c in col_names}:
        available = ", ".join(f"`{c}`" for c in sorted(col_names)) or "none documented"
        return (
            f"Column `{column_name}` does not exist in **{model_name}**.\n\n"
            f"Available columns: {available}"
        )

    # Use all_downstream_ids for transitive reach; fall back to child_ids
    all_downstream = upstream.get("all_downstream_ids") or upstream.get("child_ids", [])

    if not all_downstream:
        return (
            f"**{model_name}** has no downstream models.\n\n"
            f"Removing `{column_name}` would not break any other model."
        )

    directly_breaks: list[str] = []
    no_reference:    list[str] = []

    for child_id in all_downstream:
        child = by_id.get(child_id)
        if not child:
            continue
        child_name = child.get("model_name", child_id)
        compiled   = child.get("compiled_sql", "")
        used = _columns_used_from_upstream(compiled, [column_name])
        if used:
            directly_breaks.append(child_name)
        else:
            no_reference.append(child_name)

    lines = [f"## Impact analysis: `{column_name}` in `{model_name}`\n"]

    if not directly_breaks:
        lines.append(
            f"No downstream models directly reference `{column_name}` in their SQL — "
            f"removing it would not break any query."
        )
        if no_reference:
            lines.append(f"\nThe following {len(no_reference)} downstream models depend on **{model_name}** "
                         f"but do not reference this column:")
            lines.extend(f"- {n}" for n in sorted(no_reference))
    else:
        lines.append(f"### Models that will break ({len(directly_breaks)})")
        lines.append(f"These downstream models reference `{column_name}` directly in their SQL:\n")
        lines.extend(f"- **{n}** ({_layer_of(n)})" for n in sorted(directly_breaks))

        if no_reference:
            lines.append(f"\n### Models not directly impacted ({len(no_reference)})")
            lines.append("These downstream models do not reference this column in their SQL:")
            lines.extend(f"- {n}" for n in sorted(no_reference))

    total_checked = len(directly_breaks) + len(no_reference)
    lines.append(f"\n**Total downstream models checked:** {total_checked}")
    return "\n".join(lines)


def _analyse_upstream_lineage(
    model_name: str,
    column_name: str,
    by_name: dict,
) -> str:
    """Walk upstream DAG to find where column_name first originates."""

    # Walk upward via depends_on. At each node, check if the column is in column_names.
    # A node is the "origin" if none of its upstream models also expose this column.
    chain: list[tuple[str, str]] = []   # (model_name, "origin" | "pass_through")
    visited: set[str] = set()

    def walk(name: str) -> None:
        if name in visited:
            return
        visited.add(name)

        payload = by_name.get(name)
        if not payload:
            return

        col_names_lower = {c.lower() for c in payload.get("column_names", [])}
        if column_name.lower() not in col_names_lower:
            return  # column not exposed by this model

        depends_on = payload.get("depends_on", [])  # short model names
        upstream_with_col = [
            d for d in depends_on
            if d in by_name
            and column_name.lower() in {c.lower() for c in by_name[d].get("column_names", [])}
        ]

        if upstream_with_col:
            chain.append((name, "pass_through"))
            for upstream in upstream_with_col:
                walk(upstream)
        else:
            chain.append((name, "origin"))

    walk(model_name)

    if not chain:
        return (
            f"Column `{column_name}` is not documented in **{model_name}** or any of its upstream models.\n\n"
            f"Tip: make sure columns are documented in your dbt schema YAML files."
        )

    origins       = [n for n, r in chain if r == "origin"]
    pass_throughs = [n for n, r in chain if r == "pass_through"]

    lines = [f"## Upstream lineage: `{column_name}` ← `{model_name}`\n"]

    if origins:
        origin_labels = ", ".join(f"`{o}` ({_layer_of(o)})" for o in origins)
        lines.append(f"**Column originates in:** {origin_labels}\n")

    # Build readable path: origin → ... → model_name
    # Chain is recorded top-down (model_name first, origin last); reverse for display
    ordered = list(reversed(chain))
    if len(ordered) > 1:
        path = " → ".join(f"`{n}`" for n, _ in ordered)
        lines.append(f"### Lineage path\n{path}\n")

    if origins:
        origin_name = origins[0]
        origin_payload = by_name.get(origin_name, {})
        desc = origin_payload.get("description", "")
        lines.append(f"### Origin model: `{origin_name}`")
        lines.append(f"**Layer:** {_layer_of(origin_name)}")
        if desc:
            lines.append(f"**Description:** {desc}")
        origin_cols = origin_payload.get("column_names", [])
        if column_name.lower() in {c.lower() for c in origin_cols}:
            lines.append(f"`{column_name}` is defined as a documented output column of `{origin_name}`.")

    if pass_throughs:
        lines.append(f"\n### Pass-through models ({len(pass_throughs)})")
        lines.append("These models select and re-expose the column without changing it:")
        lines.extend(f"- `{n}` ({_layer_of(n)})" for n in pass_throughs if n != model_name)

    return "\n".join(lines)


def _analyse_column_trace(
    model_name: str,
    column_name: str,
    by_name: dict,
    by_id: dict,
) -> str:
    """Full bidirectional trace: upstream origin + downstream impact for a column."""
    target = by_name.get(model_name)
    if not target:
        return f"Model **{model_name}** not found in the index."

    lines = [f"# Column trace: `{column_name}` through `{model_name}`\n"]

    # ── Upstream section ──────────────────────────────────────────────
    upstream_section = _analyse_upstream_lineage(model_name, column_name, by_name)
    # strip the H2 heading and fold into H3
    upstream_body = upstream_section.replace(
        f"## Upstream lineage: `{column_name}` ← `{model_name}`\n", ""
    ).strip()
    lines.append("## Upstream lineage")
    lines.append(upstream_body)

    # ── Downstream section ────────────────────────────────────────────
    col_names = target.get("column_names", [])
    all_downstream = target.get("all_downstream_ids") or target.get("child_ids", [])

    lines.append("\n## Downstream impact")

    if not all_downstream:
        lines.append(f"`{model_name}` is a leaf node — no downstream models.")
    else:
        uses: list[str]      = []
        no_use: list[str]    = []
        no_sql: list[str]    = []

        for child_id in all_downstream:
            child = by_id.get(child_id)
            if not child:
                continue
            child_name = child.get("model_name", child_id)
            compiled   = child.get("compiled_sql", "")
            if not compiled:
                no_sql.append(child_name)
                continue
            if _columns_used_from_upstream(compiled, [column_name]):
                uses.append(child_name)
            else:
                no_use.append(child_name)

        if uses:
            lines.append(f"\n### Directly references `{column_name}` ({len(uses)} models)")
            lines.extend(f"- **{n}** ({_layer_of(n)})" for n in sorted(uses))

        if no_use:
            lines.append(f"\n### Downstream but does not use `{column_name}` ({len(no_use)} models)")
            lines.extend(f"- {n} ({_layer_of(n)})" for n in sorted(no_use))

        if no_sql:
            lines.append(f"\n### Skipped (no compiled SQL): {', '.join(no_sql)}")

        total_down = len(uses) + len(no_use) + len(no_sql)
        lines.append(f"\n**Total downstream models:** {total_down} | "
                     f"**Directly using `{column_name}`:** {len(uses)}")

    return "\n".join(lines)


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
