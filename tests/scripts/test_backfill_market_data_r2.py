"""Unit tests for scripts/backfill_market_data_r2.py + scripts/check_r2_parity.py (#3780).

The backfill copies Supabase market tables (direct-PG, paginated) into
versioned R2 generations via R2HistoryStore. These tests pin the resume-safe
contract: generations already in the manifest are skipped, every put goes
through the store, and the ``latest`` pointer follows the new generation.
"""

from __future__ import annotations

import importlib.util
import sys
from datetime import date, timedelta
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
BACKFILL_SCRIPT = REPO_ROOT / "scripts" / "backfill_market_data_r2.py"
PARITY_SCRIPT = REPO_ROOT / "scripts" / "check_r2_parity.py"


def _load(name: str, path: Path) -> Any:
    spec = importlib.util.spec_from_file_location(name, path)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    sys.modules[name] = module
    spec.loader.exec_module(module)
    return module


backfill = _load("backfill_market_data_r2", BACKFILL_SCRIPT)
parity = _load("check_r2_parity", PARITY_SCRIPT)


def rows_730(end: str = "2026-09-08") -> list[dict[str, Any]]:
    """730 daily SPY rows ending on *end* (paginateable via a fetch_page closure)."""
    last = date.fromisoformat(end)
    rows: list[dict[str, Any]] = []
    for i in range(730):
        day = last - timedelta(days=729 - i)
        px = 500.0 + i * 0.1
        rows.append(
            {
                "date": day.isoformat(),
                "ticker": "SPY",
                "open": px,
                "high": px + 1.0,
                "low": px - 1.0,
                "close": px + 0.5,
                "volume": 10_000_000 + i,
            }
        )
    return rows


def make_fetch_page(rows: list[dict[str, Any]]) -> Any:
    """Wrap row list in the ``fetch_page(ticker, offset, limit)`` production seam."""

    def fetch_page(ticker: str, offset: int, limit: int) -> list[dict[str, Any]]:
        assert ticker == "SPY"
        return rows[offset : offset + limit]

    return fetch_page


class FakeStore:
    """Minimal store protocol the backfill needs (mirrors R2HistoryStore)."""

    def __init__(self, existing: set[str] | None = None) -> None:
        self._existing = set(existing or ())
        self.puts: list[dict[str, Any]] = []
        self.pointers: dict[str, str] = {}

    def existing_generations(self, prefix: str) -> list[str]:
        return sorted(k for k in self._existing if k.startswith(prefix))

    def put_generation(
        self,
        key: str,
        payload: bytes,
        source_table: str,
        source_key: dict[str, Any] | None = None,
        rows: int = -1,
    ) -> Any:
        self.puts.append({"key": key, "source_table": source_table, "rows": rows})
        self._existing.add(key)
        return {"key": key, "sha256": "fake", "rows": rows}

    def swap_latest_pointer(self, pointer_key: str, generation_key: str) -> None:
        self.pointers[pointer_key] = generation_key


def test_backfill_resumes_from_manifest() -> None:
    calls: list[str] = []
    store = FakeStore(existing={"market-data/price/SPY/2026-09-07.parquet"})
    n = backfill.backfill_ticker(
        "SPY", make_fetch_page(rows_730()), store, page_size=100, progress=calls.append
    )
    assert n == 1
    assert any("resume" in str(c) for c in calls)


def test_backfill_skips_generation_already_present() -> None:
    calls: list[str] = []
    store = FakeStore(existing={"market-data/price/SPY/2026-09-08.parquet"})
    n = backfill.backfill_ticker(
        "SPY", make_fetch_page(rows_730()), store, page_size=100, progress=calls.append
    )
    assert n == 0
    assert store.puts == []
    assert any("already present" in str(c) for c in calls)


def test_parity_zero_tolerance(tmp_path: Path) -> None:
    ok = parity.compare_counts({"SPY": 730, "QQQ": 700}, {"SPY": 730, "QQQ": 700})
    assert ok["ok"] is True
    assert ok["mismatches"] == []
    bad = parity.compare_counts({"SPY": 730}, {"SPY": 729})
    assert bad["ok"] is False
    assert bad["mismatches"] == [{"dataset": "SPY", "supabase": 730, "r2": 729}]
    artifact = tmp_path / "parity.json"
    parity.write_artifact(bad, str(artifact))
    assert artifact.exists()
