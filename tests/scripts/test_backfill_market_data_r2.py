"""Unit tests for scripts/backfill_market_data_r2.py + scripts/check_r2_parity.py (#3780).

The backfill copies Supabase market tables (direct-PG, paginated) into
versioned R2 generations via R2HistoryStore. These tests pin the resume-safe
contract: generations already in the manifest are skipped, every put goes
through the store, and the ``latest`` pointer follows the new generation.
"""

from __future__ import annotations

import importlib.util
import io
import sys
from datetime import date, timedelta
from decimal import Decimal
from pathlib import Path
from typing import Any  # score:allow untyped any — dynamically loaded module

import polars as pl
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


def test_to_parquet_bytes_decimal_ohlcv_float_schema() -> None:
    """Direct-PG yields Decimal for numeric OHLCV: parquet must be Float64/Int64."""
    px = [Decimal("500.10"), Decimal("501.25"), Decimal("499.75")]
    rows = [
        {
            "date": f"2026-09-0{6 + i}",
            "ticker": "SPY",
            "open": p,
            "high": p + Decimal("1.0"),
            "low": p - Decimal("1.0"),
            "close": p + Decimal("0.5"),
            "volume": 10_000_000 + i,
        }
        for i, p in enumerate(px)
    ]
    frame = pl.read_parquet(io.BytesIO(backfill.to_parquet_bytes(rows)))
    assert frame.schema["date"] == pl.Date
    assert frame.schema["open"] == pl.Float64
    assert frame.schema["high"] == pl.Float64
    assert frame.schema["low"] == pl.Float64
    assert frame.schema["close"] == pl.Float64
    assert frame.schema["volume"] == pl.Int64
    assert frame["ticker"].to_list() == ["SPY"] * 3


def macro_rows_730(end: str = "2026-09-08") -> list[dict[str, Any]]:
    """730 daily FRED DGS10 observations ending on *end* (obs_date, not date)."""
    last = date.fromisoformat(end)
    return [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": (last - timedelta(days=729 - i)).isoformat(),
            "value": 4.0 + i * 0.001,
            "unit": "percent",
        }
        for i in range(730)
    ]


def make_macro_fetch(rows: list[dict[str, Any]]) -> Any:
    """Wrap row list in the ``fetch_page(offset, limit)`` macro production seam."""

    def fetch_page(offset: int, limit: int) -> list[dict[str, Any]]:
        return rows[offset : offset + limit]

    return fetch_page


def test_backfill_macro_lowercases_uppercase_source() -> None:
    """Upper-case spec sources must still write lowercase keys/pointers (#3780).

    The refresh (``refresh_macro_series``) and the reader
    (``_read_r2_macro_window`` hardcodes ``"fred"``) both lowercase, so an
    upper-case ``backfill_macro`` source would write unreachable
    keys/pointers. Regression net: mixed-case in, lowercase out.
    """
    calls: list[str] = []
    store = FakeStore()
    n = backfill.backfill_macro(
        "FRED",
        "DGS10",
        make_macro_fetch(macro_rows_730()),
        store,
        page_size=100,
        progress=calls.append,
    )
    assert n == 1
    assert [p["key"] for p in store.puts] == ["market-data/macro/fred__DGS10/2026-09-08.parquet"]
    assert store.pointers == {
        "market-data/macro/fred__DGS10/latest": "market-data/macro/fred__DGS10/2026-09-08.parquet"
    }


def test_r2_store_adapter_macro_dataset_id_lowercases_source() -> None:
    """Adapter manifest ids normalize the source the same way (``fred__DGS10``)."""
    from types import SimpleNamespace

    class Inner:
        def put_generation(
            self,
            key: str,
            payload: bytes,
            source_table: str,
            source_key: dict[str, Any] | None = None,
            rows: int = -1,
        ) -> Any:
            return SimpleNamespace(key=key, sha256="abc123")

    manifest: dict[str, Any] = {}
    adapter = backfill.R2StoreAdapter(Inner(), manifest)
    adapter.put_generation(
        "market-data/macro/fred__DGS10/2026-09-08.parquet",
        b"macro-bytes",
        backfill.SOURCE_TABLE_MACRO,
        {"source": "FRED", "series": "DGS10", "as_of": "2026-09-08"},
        rows=730,
    )
    assert list(manifest["datasets"]) == ["fred__DGS10"]


def test_backfill_macro_resumes_from_manifest() -> None:
    calls: list[str] = []
    store = FakeStore(existing={"market-data/macro/fred__DGS10/2026-09-07.parquet"})
    n = backfill.backfill_macro(
        "fred",
        "DGS10",
        make_macro_fetch(macro_rows_730()),
        store,
        page_size=100,
        progress=calls.append,
    )
    assert n == 1
    assert any("resume" in str(c) for c in calls)


def test_r2_store_adapter_dataset_ids_and_entry_shape() -> None:
    """Task 7 contract: normalized-ticker / SRC__SERIES ids, fixed entry shape."""
    from types import SimpleNamespace

    class Inner:
        def put_generation(
            self,
            key: str,
            payload: bytes,
            source_table: str,
            source_key: dict[str, Any] | None = None,
            rows: int = -1,
        ) -> Any:
            return SimpleNamespace(key=key, sha256="abc123")

    manifest: dict[str, Any] = {}
    adapter = backfill.R2StoreAdapter(Inner(), manifest)
    adapter.put_generation(
        "market-data/price/BRK-B/2026-09-08.parquet",
        b"price-bytes",
        backfill.SOURCE_TABLE_PRICE,
        {"ticker": "brk/b", "as_of": "2026-09-08"},
        rows=730,
    )
    adapter.put_generation(
        "market-data/macro/fred__DGS10/2026-09-08.parquet",
        b"macro-bytes",
        backfill.SOURCE_TABLE_MACRO,
        {"source": "fred", "series": "DGS10", "as_of": "2026-09-08"},
        rows=730,
    )
    assert manifest["datasets"]["BRK-B"] == {
        "object": "market-data/price/BRK-B/2026-09-08.parquet",
        "sha256": "abc123",
        "rows": 730,
        "as_of": "2026-09-08",
    }
    assert manifest["datasets"]["fred__DGS10"] == {
        "object": "market-data/macro/fred__DGS10/2026-09-08.parquet",
        "sha256": "abc123",
        "rows": 730,
        "as_of": "2026-09-08",
    }


def test_parity_extra_in_r2_fails_gate() -> None:
    """Stray R2 datasets fail the Task 7 gate: extras are NOT tolerated."""
    report = parity.compare_counts({"SPY": 730}, {"SPY": 730, "STRAY": 10})
    assert report["extra_in_r2"] == ["STRAY"]
    assert report["ok"] is False


def test_parity_missing_excluded_from_mismatches() -> None:
    report = parity.compare_counts({"SPY": 730}, {})
    assert report["missing_in_r2"] == ["SPY"]
    assert report["mismatches"] == []
    assert report["ok"] is False


class _FakeHistoryStore:
    """Minimal R2HistoryStore surface for main()'s manifest load/save."""

    def __init__(self, exc: Exception | None = None) -> None:
        self._exc = exc

    def read_manifest(self) -> dict[str, Any]:
        if self._exc is not None:
            raise self._exc
        return backfill.build_manifest("1970-01-01", {})

    def write_manifest(self, manifest: dict[str, Any]) -> str:
        return "deadbeef"


def _run_main(tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception) -> int:
    monkeypatch.setattr(backfill, "R2Backend", lambda **kw: object())
    monkeypatch.setattr(backfill, "R2HistoryStore", lambda b, i: _FakeHistoryStore(exc))
    monkeypatch.setattr(backfill, "_pg_registry_insert", lambda uri: lambda *a: None)
    monkeypatch.setattr(backfill, "make_price_fetcher", lambda uri: lambda tk, off, lim: [])
    for env in (
        backfill.R2_ACCOUNT_ENV,
        backfill.R2_BUCKET_ENV,
        backfill.R2_ACCESS_KEY_ENV,
        backfill.R2_SECRET_KEY_ENV,
    ):
        monkeypatch.setenv(env, "test")
    return backfill.main(
        [
            "--tickers",
            "SPY",
            "--postgres-uri",
            "postgresql://fake",
            "--manifest-out",
            str(tmp_path / "m.json"),
        ]
    )


@pytest.mark.parametrize(
    "exc",
    [
        RuntimeError("creds boom"),
        ConnectionError("net down"),
        ValueError("bad manifest version"),
    ],
)
def test_main_manifest_non_missing_error_propagates(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, exc: Exception
) -> None:
    """Narrow except: creds/network/corrupt-manifest errors must surface, not fresh-start."""
    with pytest.raises(type(exc)):
        _run_main(tmp_path, monkeypatch, exc)


def test_main_missing_manifest_starts_fresh(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, capsys: pytest.CaptureFixture[str]
) -> None:
    rc = _run_main(tmp_path, monkeypatch, FileNotFoundError("no manifest yet"))
    assert rc == 0
    assert "starting fresh" in capsys.readouterr().out
    assert (tmp_path / "m.json").exists()
