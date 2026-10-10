"""Unit tests for analytics tools: load_dataset, summary_stats, plot_distribution."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digigraph.tools.analytics import filter_dataset, load_dataset, plot_distribution, summary_stats


@pytest.fixture
def sample_dataset_path(tmp_path: Path) -> str:
    """Write a small JSON dataset and return path."""
    data = [
        {"content": "a", "score": 0.5, "doc_id": "d1", "rank": 1, "metadata": {"sourceType": "EXCHANGE", "sentDateTime": "2025-01-01"}},
        {"content": "b", "score": 0.8, "doc_id": "d2", "rank": 2, "metadata": {"sourceType": "TEAMS", "sentDateTime": "2025-01-02"}},
    ]
    path = tmp_path / "data.json"
    path.write_text(json.dumps(data), encoding="utf-8")
    return str(path)


@pytest.mark.unit
def test_load_dataset(sample_dataset_path: str) -> None:
    df = load_dataset(sample_dataset_path)
    assert len(df) == 2
    assert "score" in df.columns
    assert "sourceType" in df.columns


@pytest.mark.unit
def test_summary_stats(sample_dataset_path: str) -> None:
    out = summary_stats(sample_dataset_path)
    assert "stats" in out
    assert "score" in out["stats"]
    assert out["stats"]["score"].get("mean") is not None


@pytest.mark.unit
def test_filter_dataset_unknown_op_returns_error_and_does_not_write(
    sample_dataset_path: str,
) -> None:
    out = filter_dataset(
        sample_dataset_path,
        [{"field": "score", "op": "contains", "value": 0.5}],
    )
    assert out["error"] == "unknown filter op 'contains'"
    assert out["dataset_ref"] is None
    assert out["rows"] == 0
    assert not (Path(sample_dataset_path).parent / "filtered.json").exists()


@pytest.mark.unit
def test_filter_dataset_missing_op_defaults_to_eq(sample_dataset_path: str) -> None:
    out = filter_dataset(sample_dataset_path, [{"field": "score", "value": 0.5}])
    assert out["rows"] == 1
    assert "error" not in out
    assert Path(out["dataset_ref"]).is_file()


@pytest.mark.unit
def test_filter_dataset_empty_filters_returns_the_frame(sample_dataset_path: str) -> None:
    out = filter_dataset(sample_dataset_path, [])
    assert out["rows"] == 2
    assert "error" not in out


@pytest.mark.unit
def test_plot_distribution(sample_dataset_path: str) -> None:
    out = plot_distribution(sample_dataset_path, "score", "histogram")
    assert "summary" in out
    assert out["summary"].get("count") == 2
    if out.get("image_path"):
        assert Path(out["image_path"]).exists()
