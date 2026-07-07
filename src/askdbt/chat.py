"""Streamlit chat UI for askdbt."""

from __future__ import annotations

import os

import streamlit as st

try:
    from .config import Config
    from .retriever import Retriever
except ImportError:
    import sys
    from pathlib import Path
    sys.path.insert(0, str(Path(__file__).parent.parent))
    from askdbt.config import Config
    from askdbt.retriever import Retriever


def _config_from_env() -> Config:
    cfg = Config()
    cfg.vector_db = os.getenv("ASKDBT_VECTOR_DB", cfg.vector_db)
    cfg.qdrant_host = os.getenv("ASKDBT_QDRANT_HOST", cfg.qdrant_host)
    cfg.qdrant_port = int(os.getenv("ASKDBT_QDRANT_PORT", str(cfg.qdrant_port)))
    cfg.qdrant_collection = os.getenv("ASKDBT_QDRANT_COLLECTION", cfg.qdrant_collection)
    cfg.pg_dsn = os.getenv("ASKDBT_PG_DSN", cfg.pg_dsn)
    cfg.ollama_model = os.getenv("ASKDBT_OLLAMA_MODEL", cfg.ollama_model)
    cfg.ollama_base_url = os.getenv("ASKDBT_OLLAMA_URL", cfg.ollama_base_url)
    return cfg


@st.cache_resource
def get_retriever() -> Retriever:
    return Retriever(_config_from_env())


def main():
    st.set_page_config(page_title="askdbt", page_icon="🤖", layout="centered")

    st.title("🤖 askdbt")
    st.caption("AI-powered data dictionary powered by your dbt manifest — 100% local via Ollama")

    # Sidebar settings
    with st.sidebar:
        st.header("Settings")
        cfg = _config_from_env()
        st.markdown(f"**LLM:** `{cfg.ollama_model}` via Ollama")
        st.markdown(f"**Vector DB:** `{cfg.vector_db}`")
        st.markdown(f"**Embeddings:** `{cfg.embedding_model}`")
        st.divider()
        st.markdown("**Example questions**")
        examples = [
            "How many models are in this project?",
            "List all staging models",
            "Which columns of dim_customers aren't used downstream?",
            "What does the ecl_provision column mean?",
            "What breaks if I remove customer_id from dim_customers?",
            "Where does customer_id come from in mart_customer_360?",
        ]
        for q in examples:
            if st.button(q, use_container_width=True, key=q):
                st.session_state["prefill"] = q

    # Chat history
    if "messages" not in st.session_state:
        st.session_state["messages"] = []

    for msg in st.session_state["messages"]:
        with st.chat_message(msg["role"]):
            st.markdown(msg["content"])
            if msg.get("sources"):
                st.caption("Sources: " + ", ".join(f"`{s}`" for s in msg["sources"]))

    # Input
    prefill = st.session_state.pop("prefill", "")
    question = st.chat_input("Ask anything about your dbt models…") or prefill

    if question:
        st.session_state["messages"].append({"role": "user", "content": question})
        with st.chat_message("user"):
            st.markdown(question)

        with st.chat_message("assistant"):
            with st.spinner("Thinking…"):
                retriever = get_retriever()
                result = retriever.ask(question)

            st.markdown(result.answer)
            if result.sources:
                st.caption("Sources: " + ", ".join(f"`{s}`" for s in result.sources))

        st.session_state["messages"].append({
            "role": "assistant",
            "content": result.answer,
            "sources": result.sources,
        })


if __name__ == "__main__":
    main()
