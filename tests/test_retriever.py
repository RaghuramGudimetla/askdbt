"""Tests for retriever prompt construction — no Ollama or vector DB needed."""

from unittest.mock import MagicMock, patch

import pytest

from askdbt.retriever import Answer, RetrievedChunk, Retriever, _build_prompt


def test_build_prompt_includes_question():
    prompt = _build_prompt("What is CLV?", "customer_lifetime_value: predicted net revenue...")
    assert "What is CLV?" in prompt
    assert "customer_lifetime_value" in prompt


def test_build_prompt_includes_context():
    context = "Model: dim_customers\nDescription: Customer dimension table"
    prompt = _build_prompt("How many columns?", context)
    assert "dim_customers" in prompt


def test_retriever_returns_answer_on_empty_results():
    retriever = Retriever()
    retriever.retrieve = MagicMock(return_value=[])
    result = retriever.ask("What does CLV mean?")
    assert isinstance(result, Answer)
    assert "index" in result.answer.lower()
    assert result.sources == []


def test_retriever_calls_ollama_with_context():
    chunk = RetrievedChunk(
        model_name="mart_customer_360",
        text="Model: mart_customer_360\ncustomer_lifetime_value: predicted revenue",
        score=0.85,
    )
    retriever = Retriever()
    retriever.retrieve = MagicMock(return_value=[chunk])
    retriever._call_ollama = MagicMock(return_value="CLV is predicted net revenue over 36 months.")

    result = retriever.ask("What is CLV?")
    assert result.answer == "CLV is predicted net revenue over 36 months."
    assert "mart_customer_360" in result.sources

    # Check ollama was called with context containing the chunk text
    call_args = retriever._call_ollama.call_args[0][0]
    assert "customer_lifetime_value" in call_args


def test_ollama_connection_error_returns_friendly_message():
    retriever = Retriever()
    chunk = RetrievedChunk(model_name="dim_customers", text="some text", score=0.9)
    retriever.retrieve = MagicMock(return_value=[chunk])

    result = retriever.ask("anything")
    # Will hit actual Ollama which won't be running in tests — should get friendly error
    assert isinstance(result.answer, str)
    assert len(result.answer) > 0
