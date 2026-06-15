"""Tests for ManifestParser — no network, no vector DB required."""

from pathlib import Path

import pytest

from askdbt.parser import ManifestParser, ModelChunk

SAMPLE_MANIFEST = Path(__file__).parent.parent / "sample_data" / "manifest.json"


@pytest.fixture
def chunks() -> list[ModelChunk]:
    parser = ManifestParser(SAMPLE_MANIFEST)
    return parser.parse()


def test_parse_returns_models(chunks):
    assert len(chunks) == 6


def test_model_names(chunks):
    names = {c.model_name for c in chunks}
    assert "dim_customers" in names
    assert "fct_transactions" in names
    assert "mart_customer_360" in names


def test_columns_parsed(chunks):
    dim_customers = next(c for c in chunks if c.model_name == "dim_customers")
    col_names = [c.name for c in dim_customers.columns]
    assert "customer_id" in col_names
    assert "kyc_status" in col_names
    assert "risk_tier" in col_names


def test_description_non_empty(chunks):
    for chunk in chunks:
        assert chunk.description, f"{chunk.model_name} has no description"


def test_to_text_contains_model_name(chunks):
    for chunk in chunks:
        text = chunk.to_text()
        assert chunk.model_name in text


def test_to_text_contains_column_descriptions(chunks):
    fct = next(c for c in chunks if c.model_name == "fct_transactions")
    text = fct.to_text()
    assert "fraud" in text.lower()
    assert "merchant" in text.lower()


def test_tags_parsed(chunks):
    fct = next(c for c in chunks if c.model_name == "fct_loan_repayments")
    assert "ifrs9" in fct.tags


def test_materialization(chunks):
    dim = next(c for c in chunks if c.model_name == "dim_customers")
    assert dim.materialization == "table"

    fct = next(c for c in chunks if c.model_name == "fct_transactions")
    assert fct.materialization == "incremental"


def test_depends_on_model_links(chunks):
    mart = next(c for c in chunks if c.model_name == "mart_customer_360")
    assert "dim_customers" in mart.depends_on
    assert "fct_transactions" in mart.depends_on


def test_chunk_id_stable():
    from askdbt.indexer import _chunk_id
    id1 = _chunk_id("model.banking.dim_customers")
    id2 = _chunk_id("model.banking.dim_customers")
    assert id1 == id2


def test_chunk_id_unique():
    from askdbt.indexer import _chunk_id
    id1 = _chunk_id("model.banking.dim_customers")
    id2 = _chunk_id("model.banking.fct_transactions")
    assert id1 != id2
