"""Unit tests for DigiSearch Polars summarization."""

from __future__ import annotations

import pytest

from digisearch.core.summarize import summarize_results


@pytest.mark.unit
def test_summarize_empty() -> None:
    out = summarize_results([], sample_size=5)
    assert out["data_summary"]["total_rows"] == 0
    assert out["sample"] == []
    assert "0 results" in out["text_summary"]


@pytest.mark.unit
def test_summarize_small_result_set() -> None:
    results = [
        {"content": "Hello world", "score": 0.9, "doc_id": "d1", "rank": 1, "metadata": {"sourceType": "EXCHANGE", "sentDateTime": "2025-01-01T00:00:00Z"}},
        {"content": "Second doc", "score": 0.8, "doc_id": "d2", "rank": 2, "metadata": {"sourceType": "TEAMS", "sentDateTime": "2025-01-02T00:00:00Z"}},
    ]
    out = summarize_results(results, sample_size=5, include_text_summary=True)
    assert out["data_summary"]["total_rows"] == 2
    assert "sourceType" in out["data_summary"]["categorical_top"] or "sourceType" in out["data_summary"]["counts"]
    assert len(out["sample"]) <= 2
    assert "2 results" in out["text_summary"]


@pytest.mark.unit
def test_summarize_numeric_and_categorical() -> None:
    results = [
        {"content": "a", "score": 0.5, "doc_id": "1", "rank": 1, "metadata": {"sourceType": "EXCHANGE", "count": 10}},
        {"content": "b", "score": 0.6, "doc_id": "2", "rank": 2, "metadata": {"sourceType": "EXCHANGE", "count": 20}},
        {"content": "c", "score": 0.7, "doc_id": "3", "rank": 3, "metadata": {"sourceType": "TEAMS", "count": 15}},
    ]
    out = summarize_results(results, categorical_top_k=5)
    assert out["data_summary"]["total_rows"] == 3
    assert "score" in out["data_summary"]["numeric_stats"]
    assert out["data_summary"]["numeric_stats"]["score"]["min"] == 0.5
    assert out["data_summary"]["numeric_stats"]["score"]["max"] == 0.7
    assert len(out["data_summary"]["categorical_top"].get("sourceType", [])) >= 1
    assert out["data_summary"]["counts"]["sourceType"] == 3
