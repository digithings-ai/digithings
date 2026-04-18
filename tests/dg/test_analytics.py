"""Unit tests for analytics tools: load_dataset, summary_stats, plot_distribution."""

from __future__ import annotations

import json
import tempfile
from pathlib import Path

import pytest

from digigraph.tools.analytics import load_dataset, plot_distribution, summary_stats


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
def test_plot_distribution(sample_dataset_path: str) -> None:
    out = plot_distribution(sample_dataset_path, "score", "histogram")
    assert "summary" in out
    assert out["summary"].get("count") == 2
    if out.get("image_path"):
        assert Path(out["image_path"]).exists()
