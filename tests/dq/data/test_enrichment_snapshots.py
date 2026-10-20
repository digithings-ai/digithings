"""Unit tests for the gloomberb enrichment snapshot store (#4804)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest
from digiquant.data.enrichment.snapshots import (
    load_latest,
    merge_series_page,
    prune_tool,
    snapshot_root,
    write_snapshot,
)

pytestmark = pytest.mark.unit


def test_write_then_load_latest_round_trip(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    path = write_snapshot(
        "digifetch_news", {"ticker": "GLD"}, '{"data": []}', fetched_at="2026-09-30T12:00:00Z"
    )
    assert path.parent.name == "digifetch_news"
    latest = load_latest("digifetch_news")
    assert latest is not None
    doc = json.loads(Path(latest).read_text(encoding="utf-8"))
    assert doc["tool"] == "digifetch_news"
    assert doc["params"] == {"ticker": "GLD"}
    assert doc["fetched_at"] == "2026-09-30T12:00:00Z"
    assert doc["source"] == "gloomberb"
    assert "delay" in doc["delay_notice"].lower()
    assert "gloomberb" in doc["attribution"].lower()
    assert json.loads(doc["payload"]) == {"data": []}


def test_load_latest_missing_tool_returns_none(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    assert load_latest("digifetch_nope") is None


def test_prune_tool_keeps_newest_n(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    for day in ("01", "02", "03"):
        write_snapshot(
            "digifetch_news", {"ticker": "GLD"}, "{}", fetched_at=f"2026-09-{day}T12:00:00Z"
        )
    removed = prune_tool("digifetch_news", keep=2)
    assert removed == 1
    assert (
        len(list((snapshot_root() / "digifetch_news").glob("*.json"))) == 3
    )  # 2 pages + latest.json


def test_prune_tool_removes_metrics_companion_with_page(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    pages = [
        write_snapshot(
            "digifetch_news", {"ticker": "GLD"}, "{}", fetched_at=f"2026-09-{day}T12:00:00Z"
        )
        for day in ("01", "02", "03")
    ]
    for page in pages:
        (page.parent / f"{page.stem}.metrics.json").write_text("{}", encoding="utf-8")
    removed = prune_tool("digifetch_news", keep=2)
    assert removed == 1
    assert not pages[0].exists()
    assert not (pages[0].parent / f"{pages[0].stem}.metrics.json").exists()
    tool_dir = snapshot_root() / "digifetch_news"
    data_pages = [
        p for p in tool_dir.glob("[0-9]*__*.json") if not p.name.endswith(".metrics.json")
    ]
    assert len(data_pages) == 2
    assert len(list(tool_dir.glob("*.metrics.json"))) == 2
    assert (tool_dir / "latest.json").is_file()


def test_merge_series_page_appends_newer_obs_only(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    monkeypatch.setenv("DIGIQUANT_ENRICHMENT_DIR", str(tmp_path))
    first = [{"date": "2024-01-01", "value": 1.0}, {"date": "2024-01-02", "value": 2.0}]
    page = [{"date": "2024-01-02", "value": 2.0}, {"date": "2024-01-03", "value": 3.0}]
    merged = merge_series_page(first, page)
    assert [r["date"] for r in merged] == ["2024-01-01", "2024-01-02", "2024-01-03"]
    with pytest.raises(ValueError, match="empty page"):
        merge_series_page(first, [])
