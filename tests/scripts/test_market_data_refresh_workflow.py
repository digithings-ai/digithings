"""Unit tests for scripts/refresh_market_data_r2.py + refresh workflow (#3780, Task 6).

The daily refresh merges vendor live overlap into new immutable R2
generations. Restatements trigger a full re-pull; fetch failures serve
history-only (previous objects untouched, manifest stale); one ticker's
failure never aborts the rest of the universe; registry conflicts re-pull
and recompute but NEVER overwrite the existing object.
"""

from __future__ import annotations

import json
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest
import yaml

pytestmark = pytest.mark.unit

from digiquant.data.prices.r2_history import (  # noqa: E402
    SOURCE_TABLE_MACRO,
    normalize_ticker,
)
from digiquant.ops.checkpoint_archive import ArchiveVerifyError  # noqa: E402

from scripts.refresh_market_data_r2 import (  # noqa: E402
    _SOFT_FAIL_MODES,
    FetchError,
    refresh_macro_series,
    refresh_ticker,
    refresh_universe,
)

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline-market-data-refresh.yml"

HIST_DEFAULT = [
    ("2025-12-29", 100.0),
    ("2025-12-30", 101.0),
    ("2025-12-31", 102.0),
    ("2026-01-01", 103.0),
    ("2026-01-02", 104.0),
]


def price_rows(dates_closes: list[tuple[str, float]], ticker: str = "SPY") -> list[dict]:
    return [
        {
            "date": d,
            "ticker": ticker,
            "open": c - 0.5,
            "high": c + 0.5,
            "low": c - 1.0,
            "close": c,
            "volume": 1000,
        }
        for d, c in dates_closes
    ]


def price_frame(rows: list[dict]) -> pl.DataFrame:
    return pl.DataFrame(rows).with_columns(
        pl.col("date").cast(pl.Date),
        pl.col("open").cast(pl.Float64),
        pl.col("high").cast(pl.Float64),
        pl.col("low").cast(pl.Float64),
        pl.col("close").cast(pl.Float64),
        pl.col("volume").cast(pl.Int64),
    )


class FakeStore:
    """Duck-typed refresh store: canned history/live frames + write ledger."""

    def __init__(
        self,
        histories: dict[str, list[dict]] | None = None,
        lives: dict[str, list[dict]] | None = None,
        fulls: dict[str, list[dict]] | None = None,
        macros: dict[tuple[str, str], list[dict]] | None = None,
        macro_lives: dict[tuple[str, str], list[dict]] | None = None,
        history_hash: str = "old",
        live_rewritten_history: list[dict] | None = None,
        fetch_errors: dict[str, str] | None = None,
        fetch_raises: dict[str, Exception] | None = None,
        fail_put_once: bool = False,
        always_conflict: bool = False,
        existing: set[str] | None = None,
        objects: dict[str, bytes] | None = None,
        repull_extra: list[dict] | None = None,
        manifest: dict[str, Any] | None = None,
    ) -> None:
        self.histories = {t: price_frame(r) for t, r in (histories or {}).items()}
        self.lives = {t: price_frame(r) for t, r in (lives or {}).items()}
        self.fulls = {t: price_frame(r) for t, r in (fulls or {}).items()}
        self.macros = dict(macros or {})
        self.macro_lives = dict(macro_lives or {})
        self.history_hash = history_hash
        self.fetch_errors = dict(fetch_errors or {})
        self.fetch_raises = dict(fetch_raises or {})
        self.fail_put_once = fail_put_once
        self.always_conflict = always_conflict
        self.existing = set(existing or ())
        self.objects = dict(objects or {})
        self.repull_extra = list(repull_extra or [])
        self.manifest = manifest
        self.puts: list[dict[str, Any]] = []
        self.pointers: dict[str, str] = {}
        self.full_calls: dict[str, int] = {}
        self.macro_full_calls: dict[tuple[str, str], int] = {}
        self.macro_windows: list[tuple[str, str, str, str]] = []
        if live_rewritten_history is not None:
            base = {r["date"]: dict(r) for r in price_rows(HIST_DEFAULT)}
            for row in live_rewritten_history:
                merged = dict(base.get(row["date"], {"ticker": "SPY", "volume": 1000}))
                merged.update(row)
                base[row["date"]] = merged
            ordered = [base[d] for d in sorted(base)]
            self.histories.setdefault("SPY", price_frame(price_rows(HIST_DEFAULT)))
            self.lives["SPY"] = price_frame(ordered)
            self.fulls.setdefault("SPY", price_frame(ordered))

    # -- read side ------------------------------------------------------
    def read_history(self, ticker: str) -> pl.DataFrame:
        if ticker in self.fetch_raises and self.fetch_raises[ticker] is not None:
            raise self.fetch_raises[ticker]
        try:
            return self.histories[ticker].clone()
        except KeyError:
            raise LookupError(f"unknown ticker {ticker!r}") from None

    def fetch_live(self, ticker: str, start: str, end: str) -> pl.DataFrame:
        if ticker in self.fetch_raises and self.fetch_raises[ticker] is not None:
            raise self.fetch_raises[ticker]
        if ticker in self.fetch_errors:
            raise FetchError(ticker, self.fetch_errors[ticker])
        frame = self.lives.get(ticker)
        if frame is None:
            return price_frame(price_rows([], ticker)).clear()
        return frame.filter(
            (pl.col("date") >= pl.lit(start).cast(pl.Date))
            & (pl.col("date") <= pl.lit(end).cast(pl.Date))
        )

    def fetch_live_full(self, ticker: str, end: str) -> pl.DataFrame:
        if ticker in self.fetch_errors:
            raise FetchError(ticker, self.fetch_errors[ticker])
        self.full_calls[ticker] = self.full_calls.get(ticker, 0) + 1
        frame = self.fulls.get(ticker)
        if frame is None:
            return price_frame(price_rows([], ticker)).clear()
        if self.full_calls[ticker] > 1 and self.repull_extra:
            frame = pl.concat([frame, price_frame(self.repull_extra)]).sort("date")
        return frame.filter(pl.col("date") <= pl.lit(end).cast(pl.Date))

    def read_macro(self, source: str, series: str) -> pl.DataFrame:
        try:
            return pl.DataFrame(self.macros[(source, series)])
        except KeyError:
            raise LookupError(f"unknown macro {source}/{series}") from None

    def fetch_macro(self, source: str, series: str, start: str, end: str) -> list[dict[str, Any]]:
        self.macro_windows.append((source, series, start, end))
        return list(self.macro_live_rows(source, series, start, end))

    def fetch_macro_full(self, source: str, series: str, end: str) -> list[dict[str, Any]]:
        self.macro_full_calls[(source, series)] = self.macro_full_calls.get((source, series), 0) + 1
        return list(self.macro_live_rows(source, series, "1990-01-01", end))

    def macro_live_rows(
        self, source: str, series: str, start: str, end: str
    ) -> list[dict[str, Any]]:
        return [
            r
            for r in self.macro_lives.get((source, series), [])
            if start <= str(r["obs_date"])[:10] <= end
        ]

    # -- write side (mirrors the R2HistoryStore seam + dataset registration) --
    def existing_generations(self, prefix: str) -> list[str]:
        return sorted(k for k in self.existing if k.startswith(prefix))

    def put_generation(
        self,
        key: str,
        payload: bytes,
        source_table: str,
        source_key: dict[str, Any] | None = None,
        rows: int = -1,
    ) -> Any:
        import hashlib

        if self.always_conflict or self.fail_put_once:
            self.fail_put_once = False
            raise ArchiveVerifyError(f"archive pointer conflict for {key}")
        if key in self.objects and self.objects[key] != payload:
            raise ArchiveVerifyError(f"archive pointer conflict for {key}")
        self.objects[key] = payload
        self.existing.add(key)
        digest = hashlib.sha256(payload).hexdigest()
        self.puts.append({"key": key, "source_table": source_table, "rows": rows})
        if self.manifest is not None:
            info = dict(source_key or {})
            if source_table == SOURCE_TABLE_MACRO:
                dataset_id = f"{info.get('source')}__{info.get('series')}"
            else:
                dataset_id = normalize_ticker(str(info.get("ticker", key)))
            self.manifest.setdefault("datasets", {})[dataset_id] = {
                "object": key,
                "sha256": digest,
                "rows": rows,
                "as_of": info.get("as_of", ""),
            }
        return SimpleNamespace(key=key, sha256=digest)

    def swap_latest_pointer(self, pointer_key: str, generation_key: str) -> None:
        self.pointers[pointer_key] = generation_key

    def read_manifest(self) -> dict[str, Any]:
        assert self.manifest is not None
        return self.manifest

    def write_manifest(self, manifest: dict[str, Any]) -> str:
        self.manifest = manifest
        return "fake"


def manifest(seal: str = "2026-01-02") -> dict[str, Any]:
    return {"version": 1, "as_of": seal, "datasets": {}}


def test_restatement_triggers_full_repull():
    from scripts.refresh_market_data_r2 import refresh_ticker

    store = FakeStore(
        history_hash="old", live_rewritten_history=[{"date": "2026-01-02", "close": 9.0}]
    )
    result = refresh_ticker("SPY", store)
    assert result["mode"] == "full-repull"


def test_incremental_merge_writes_new_generation() -> None:
    live = price_rows(HIST_DEFAULT) + price_rows([("2026-01-05", 105.0)])
    store = FakeStore(histories={"SPY": price_rows(HIST_DEFAULT)}, lives={"SPY": live})
    result = refresh_ticker("SPY", store, manifest("2026-01-02"), as_of="2026-01-06")
    assert result["mode"] == "incremental"
    assert result["as_of"] == "2026-01-05"
    assert len(store.puts) == 1
    assert store.puts[0]["key"] == "market-data/price/SPY/2026-01-05.parquet"
    assert store.pointers["market-data/price/SPY/latest"] == store.puts[0]["key"]


def test_up_to_date_writes_nothing() -> None:
    store = FakeStore(
        histories={"SPY": price_rows(HIST_DEFAULT)},
        lives={"SPY": price_rows(HIST_DEFAULT)},
    )
    result = refresh_ticker("SPY", store, manifest("2026-01-02"), as_of="2026-01-06")
    assert result["mode"] == "up-to-date"
    assert store.puts == []


def test_fetch_error_entry_serves_history_only() -> None:
    store = FakeStore(
        histories={"SPY": price_rows(HIST_DEFAULT)},
        fetch_errors={"SPY": "no_data"},
    )
    result = refresh_ticker("SPY", store, manifest("2026-01-02"), as_of="2026-01-06")
    assert result["mode"] == "history-only"
    assert store.puts == []
    assert store.pointers == {}


def test_unexpected_exception_is_error_outcome() -> None:
    store = FakeStore(fetch_raises={"SPY": RuntimeError("r2 down")})
    result = refresh_ticker("SPY", store, manifest("2026-01-02"), as_of="2026-01-06")
    assert result["mode"] == "error"
    assert store.puts == []


def test_universe_isolation_records_per_ticker_outcome() -> None:
    live = price_rows(HIST_DEFAULT) + price_rows([("2026-01-05", 105.0)])
    store = FakeStore(
        histories={"SPY": price_rows(HIST_DEFAULT)},
        lives={"SPY": live},
        fetch_raises={"BOOM": RuntimeError("r2 down")},
    )
    outcomes = refresh_universe(["SPY", "BOOM"], store, manifest(), as_of="2026-01-06")
    by_ticker = {o["ticker"]: o for o in outcomes}
    assert by_ticker["SPY"]["mode"] == "incremental"
    assert by_ticker["BOOM"]["mode"] == "error"
    assert len(store.puts) == 1


def test_registry_conflict_repairs_via_repull_without_overwrite() -> None:
    old_payload = b"previous-generation-bytes"
    conflict_key = "market-data/price/SPY/2026-01-02.parquet"
    manifest_doc = manifest("2026-01-02")
    store = FakeStore(
        history_hash="old",
        live_rewritten_history=[{"date": "2026-01-02", "close": 9.0}],
        fail_put_once=True,
        objects={conflict_key: old_payload},
        repull_extra=price_rows([("2026-01-05", 106.0)]),
        manifest=manifest_doc,
    )
    result = refresh_ticker("SPY", store, manifest_doc, as_of="2026-01-06")
    assert result["mode"] == "full-repull"
    # Conflicting object bytes are never replaced ...
    assert store.objects[conflict_key] == old_payload
    # ... the retry lands under a fresh key and the pointer follows it.
    assert result["as_of"] == "2026-01-05"
    assert store.pointers["market-data/price/SPY/latest"] == (
        "market-data/price/SPY/2026-01-05.parquet"
    )
    assert manifest_doc["datasets"]["SPY"]["object"] == ("market-data/price/SPY/2026-01-05.parquet")


def test_persistent_conflict_is_error_and_pointer_untouched() -> None:
    store = FakeStore(
        history_hash="old",
        live_rewritten_history=[{"date": "2026-01-02", "close": 9.0}],
        always_conflict=True,
    )
    result = refresh_ticker("SPY", store, manifest("2026-01-02"), as_of="2026-01-06")
    assert result["mode"] == "error"
    assert "conflict" in result["note"]
    assert store.pointers == {}


def test_macro_incremental_appends_new_observations() -> None:
    hist = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-01", "value": 4.0},
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 4.1},
    ]
    live = hist + [{"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-05", "value": 4.2}]
    store = FakeStore(macros={("fred", "DGS10"): hist}, macro_lives={("fred", "DGS10"): live})
    result = refresh_macro_series("fred", "DGS10", store, manifest(), as_of="2026-01-06")
    assert result["mode"] == "incremental"
    assert result["as_of"] == "2026-01-05"
    assert store.puts[0]["key"] == "market-data/macro/fred__DGS10/2026-01-05.parquet"


def test_macro_restatement_triggers_full_repull() -> None:
    hist = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 4.1},
    ]
    live = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 9.9},
    ]
    store = FakeStore(macros={("fred", "DGS10"): hist}, macro_lives={("fred", "DGS10"): live})
    result = refresh_macro_series("fred", "DGS10", store, manifest(), as_of="2026-01-06")
    assert result["mode"] == "full-repull"


def test_macro_registry_conflict_retries_once_then_errors() -> None:
    hist = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 4.1},
    ]
    live = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 9.9},
    ]
    store = FakeStore(
        macros={("fred", "DGS10"): hist},
        macro_lives={("fred", "DGS10"): live},
        always_conflict=True,
    )
    result = refresh_macro_series("fred", "DGS10", store, manifest(), as_of="2026-01-06")
    assert result["mode"] == "error"
    assert "conflict" in result["note"]
    assert store.macro_full_calls[("fred", "DGS10")] == 2
    assert store.puts == []
    assert store.pointers == {}


def test_macro_window_follows_declared_cadence() -> None:
    """#4588: a slow series fetches a window spanning more than one release.

    A 45-day window cannot see a monthly observation, so the fetch came back
    empty and the whole run was marked stale — every scheduled refresh exited 1.
    """
    hist = [{"source": "fred", "series_id": "PCEPI", "obs_date": "2026-07-01", "value": 84.0}]
    store = FakeStore(
        macros={("fred", "PCEPI"): hist},
        # FRED re-serves the July print inside the widened window; it is not
        # newer than the seal, so the series resolves up-to-date — not a fail.
        macro_lives={("fred", "PCEPI"): hist},
    )
    result = refresh_macro_series(
        "fred", "PCEPI", store, manifest(), as_of="2026-09-23", cadence="monthly"
    )
    assert store.macro_windows == [("fred", "PCEPI", "2026-05-26", "2026-09-24")]
    assert result["mode"] == "up-to-date"
    assert result["as_of"] == "2026-07-01"
    assert result["mode"] not in _SOFT_FAIL_MODES


def test_macro_window_defaults_to_daily_without_a_cadence() -> None:
    hist = [{"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 4.1}]
    store = FakeStore(macros={("fred", "DGS10"): hist})
    refresh_macro_series("fred", "DGS10", store, manifest(), as_of="2026-01-06")
    assert store.macro_windows == [("fred", "DGS10", "2025-11-22", "2026-01-07")]


def test_macro_unknown_cadence_is_loud() -> None:
    hist = [{"source": "fred", "series_id": "PCEPI", "obs_date": "2026-07-01", "value": 84.0}]
    store = FakeStore(macros={("fred", "PCEPI"): hist})
    with pytest.raises(ValueError, match="unknown cadence"):
        refresh_macro_series("fred", "PCEPI", store, manifest(), as_of="2026-09-23", cadence="60d")


def test_macro_refresh_matches_backfill_schema_without_meta() -> None:
    import io

    hist = [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-01-01",
            "value": 4.0,
            "unit": "Percent",
        },
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-01-02",
            "value": 4.1,
            "unit": "Percent",
        },
    ]
    live = hist + [
        {
            "source": "fred",
            "series_id": "DGS10",
            "obs_date": "2026-01-05",
            "value": 4.2,
            "unit": "Percent",
            "meta": {"title": "Market Yield on U.S. Treasury Securities"},
        }
    ]
    store = FakeStore(macros={("fred", "DGS10"): hist}, macro_lives={("fred", "DGS10"): live})
    result = refresh_macro_series("fred", "DGS10", store, manifest(), as_of="2026-01-06")
    assert result["mode"] == "incremental"
    key = "market-data/macro/fred__DGS10/2026-01-05.parquet"
    frame = pl.read_parquet(io.BytesIO(store.objects[key]))
    assert frame.columns == ["source", "series_id", "obs_date", "value", "unit"]


def test_overlap_hash_stable_for_equal_frames() -> None:
    from digiquant.data.prices.merge import overlap_hash

    assert overlap_hash(price_frame(price_rows(HIST_DEFAULT))) == overlap_hash(
        price_frame(price_rows(HIST_DEFAULT))
    )


# -- core macro mirror (#3780) ---------------------------------------------


class FakeCoreClient:
    """Duck-typed supabase client capturing macro upsert batches."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []
        self._table = ""

    def table(self, name: str) -> "FakeCoreClient":
        self._table = name
        return self

    def upsert(self, rows: list[dict], on_conflict: str | None = None) -> "FakeCoreClient":
        self.calls.append({"table": self._table, "rows": list(rows), "on_conflict": on_conflict})
        return self

    def execute(self) -> Any:
        return SimpleNamespace(data=[])


def test_core_mirror_writes_only_mirrored_sources() -> None:
    from scripts.refresh_market_data_r2 import mirror_macro_to_core

    store = FakeStore(
        macros={
            ("yahoo", "FX/EUR"): [
                {
                    "source": "yahoo",
                    "series_id": "FX/EUR",
                    "obs_date": "2026-09-10",
                    "value": 1.08,
                    "unit": "fx",
                },
                {
                    "source": "yahoo",
                    "series_id": "FX/EUR",
                    "obs_date": "2026-09-11",
                    "value": 1.09,
                    "unit": "fx",
                },
            ],
            ("fred", "DGS10"): [
                {
                    "source": "fred",
                    "series_id": "DGS10",
                    "obs_date": "2026-09-11",
                    "value": 4.0,
                    "unit": "Percent",
                },
            ],
        }
    )
    client = FakeCoreClient()
    summary = mirror_macro_to_core(
        store,
        [("yahoo", "FX/EUR", None), ("fred", "DGS10", None)],
        run="2026-09-16",
        client=client,
    )
    assert summary == {"rows": 2, "series": 1, "skipped": []}
    assert len(client.calls) == 1
    call = client.calls[0]
    assert call["table"] == "macro_series_observations"
    assert call["on_conflict"] == "source,series_id,obs_date"
    assert {r["series_id"] for r in call["rows"]} == {"FX/EUR"}
    assert all(r["source"] == "yahoo" and r["unit"] == "fx" for r in call["rows"])
    assert all(
        r["meta"] == {"yahoo_symbol": "EURUSD=X", "quote_convention": "USD_per_EUR"}
        for r in call["rows"]
    )


def test_core_mirror_window_drops_out_of_range_rows() -> None:
    from scripts.refresh_market_data_r2 import mirror_macro_to_core

    store = FakeStore(
        macros={
            ("yahoo", "FX/JPY"): [
                {
                    "source": "yahoo",
                    "series_id": "FX/JPY",
                    "obs_date": "2026-06-01",
                    "value": 100.0,
                    "unit": "fx",
                },
                {
                    "source": "yahoo",
                    "series_id": "FX/JPY",
                    "obs_date": "2026-09-11",
                    "value": 148.0,
                    "unit": "fx",
                },
            ]
        }
    )
    client = FakeCoreClient()
    summary = mirror_macro_to_core(
        store, [("yahoo", "FX/JPY", None)], run="2026-09-16", client=client
    )
    assert summary["rows"] == 1
    assert [r["obs_date"] for r in client.calls[0]["rows"]] == ["2026-09-11"]


def test_core_mirror_fail_soft_without_client() -> None:
    from scripts.refresh_market_data_r2 import mirror_macro_to_core

    store = FakeStore(
        macros={
            ("yahoo", "FX/GBP"): [
                {
                    "source": "yahoo",
                    "series_id": "FX/GBP",
                    "obs_date": "2026-09-11",
                    "value": 1.27,
                    "unit": "fx",
                }
            ]
        }
    )
    summary = mirror_macro_to_core(
        store, [("yahoo", "FX/GBP", None)], run="2026-09-16", client=None
    )
    assert summary["rows"] == 0
    assert summary["series"] == 0
    assert summary["skipped"] == ["yahoo__FX/GBP: no core client"]


def test_core_mirror_skips_unreadable_generation() -> None:
    from scripts.refresh_market_data_r2 import mirror_macro_to_core

    store = FakeStore()
    client = FakeCoreClient()
    summary = mirror_macro_to_core(
        store, [("yahoo", "FX/NZD", None)], run="2026-09-16", client=client
    )
    assert summary["rows"] == 0
    assert summary["skipped"] == ["yahoo__FX/NZD: LookupError"]
    assert client.calls == []


def test_main_mirrors_yahoo_fx_into_core(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    import scripts.refresh_market_data_r2 as refresh_mod

    manifest_doc = {"version": 1, "as_of": "2026-01-02", "datasets": {}}
    store = FakeStore(
        histories={"SPY": price_rows(HIST_DEFAULT)},
        lives={"SPY": price_rows(HIST_DEFAULT) + price_rows([("2026-01-05", 105.0)])},
        macros={
            ("yahoo", "FX/EUR"): [
                {
                    "source": "yahoo",
                    "series_id": "FX/EUR",
                    "obs_date": "2026-01-05",
                    "value": 1.08,
                    "unit": "fx",
                },
            ]
        },
        macro_lives={
            ("yahoo", "FX/EUR"): [
                {
                    "source": "yahoo",
                    "series_id": "FX/EUR",
                    "obs_date": "2026-01-06",
                    "value": 1.09,
                    "unit": "fx",
                },
            ]
        },
        manifest=manifest_doc,
    )
    client = FakeCoreClient()
    monkeypatch.setattr(refresh_mod, "build_store", lambda uri: (store, manifest_doc))
    monkeypatch.setattr(refresh_mod, "build_core_supabase_client", lambda: client)
    rc = refresh_mod.main(
        [
            "--tickers",
            "SPY",
            "--macro-series",
            "yahoo:FX/EUR",
            "--postgres-uri",
            "postgresql://fake",
            "--as-of",
            "2026-01-06",
            "--manifest-out",
            str(tmp_path / "refresh.json"),
        ]
    )
    assert rc == 0
    assert len(client.calls) == 1
    assert [r["series_id"] for r in client.calls[0]["rows"]] == ["FX/EUR"]
    artifact = json.loads((tmp_path / "refresh.json").read_text())
    assert artifact["core_macro_mirror"]["rows"] == 1
    assert artifact["core_macro_mirror"]["series"] == 1


def test_main_skips_mirror_with_no_macro_specs(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    import scripts.refresh_market_data_r2 as refresh_mod

    store = FakeStore(histories={"SPY": price_rows(HIST_DEFAULT)})
    client = FakeCoreClient()

    def _explode() -> Any:  # pragma: no cover - must never be called
        raise AssertionError("mirror client built without macro specs")

    monkeypatch.setattr(refresh_mod, "build_core_supabase_client", _explode)
    monkeypatch.setattr(refresh_mod, "_today_iso", lambda: "2026-01-05")
    monkeypatch.setattr(refresh_mod, "build_store", lambda uri: (store, manifest()))
    rc = refresh_mod.main(
        [
            "--tickers",
            "SPY",
            "--skip-macro",
            "--postgres-uri",
            "postgresql://fake",
            "--manifest-out",
            str(tmp_path / "refresh.json"),
        ]
    )
    assert rc in (0, 1)
    assert client.calls == []


# -- workflow YAML pins ----------------------------------------------------


def _workflow() -> dict[str, Any]:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


def test_workflow_schedule_and_dispatch() -> None:
    spec = _workflow()
    on = spec[True]  # YAML 1.1 parses the `on:` key as boolean True
    assert "workflow_dispatch" in on
    assert {entry["cron"] for entry in on["schedule"]} == {"0 13 * * *", "30 21 * * *"}


def test_workflow_concurrency_and_timeout() -> None:
    spec = _workflow()
    assert spec["concurrency"] == {"group": "market-data-refresh", "cancel-in-progress": False}
    job = spec["jobs"]["refresh"]
    assert job["runs-on"] == "ubuntu-latest"
    assert job["timeout-minutes"] == 30


def test_workflow_secrets_wired() -> None:
    env = _workflow()["jobs"]["refresh"]["env"]
    for name in (
        "R2_ACCOUNT_ID",
        "R2_BUCKET",
        "R2_ACCESS_KEY_ID",
        "R2_SECRET_ACCESS_KEY",
        "FRED_API_KEY",
    ):
        assert name in env, name
    # Recorded deviation (Task 6 report): the store seam needs the direct-PG
    # registry insert, so the workflow wires one extra secret past the brief pins.
    assert env["CORE_POSTGRES_URI"] == "${{ secrets.CORE_POSTGRES_URI }}"


def test_workflow_runs_refresh_and_uploads_manifest() -> None:
    steps = _workflow()["jobs"]["refresh"]["steps"]
    runs = [s.get("run", "") for s in steps]
    assert any("scripts/refresh_market_data_r2.py" in r for r in runs)
    assert any("--manifest-out /tmp/market-data-refresh.json" in r for r in runs)
    uploads = [s for s in steps if s.get("uses", "").startswith("actions/upload-artifact")]
    assert len(uploads) == 1
    assert uploads[0]["with"]["name"] == "market-data-refresh-manifest"
    assert uploads[0]["with"]["path"] == "/tmp/market-data-refresh.json"
    assert uploads[0]["with"]["retention-days"] == 90


# -- cron exit-code contract -------------------------------------------------


def _run_main(monkeypatch: pytest.MonkeyPatch, tmp_path: Path, store: FakeStore) -> int:
    import scripts.refresh_market_data_r2 as refresh_mod

    manifest_doc = {"version": 1, "as_of": "2026-01-02", "datasets": {}}
    store.manifest = manifest_doc
    monkeypatch.setattr(refresh_mod, "build_store", lambda uri: (store, manifest_doc))
    return refresh_mod.main(
        [
            "--tickers",
            ",".join(sorted({*store.histories, *store.lives}) or ["SPY"]),
            "--postgres-uri",
            "postgresql://fake",
            "--skip-macro",
            "--manifest-out",
            str(tmp_path / "refresh.json"),
        ]
    )


def test_main_exit_zero_and_manifest_fresh(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    live = price_rows(HIST_DEFAULT) + price_rows([("2026-01-05", 105.0)])
    store = FakeStore(histories={"SPY": price_rows(HIST_DEFAULT)}, lives={"SPY": live})
    monkeypatch.setattr("scripts.refresh_market_data_r2._today_iso", lambda: "2026-01-05")
    rc = _run_main(monkeypatch, tmp_path, store)
    assert rc == 0
    artifact = json.loads((tmp_path / "refresh.json").read_text())
    assert artifact["stale"] is False
    assert artifact["as_of"] == "2026-01-05"
    assert artifact["gate"] == {"ok": True, "stale_days": 0}


def test_main_marks_stale_and_exits_nonzero_on_ticker_failure(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    live = price_rows(HIST_DEFAULT) + price_rows([("2026-01-05", 105.0)])
    store = FakeStore(
        histories={"SPY": price_rows(HIST_DEFAULT)},
        lives={"SPY": live, "BOOM": price_rows(HIST_DEFAULT)},
        fetch_errors={"BOOM": "no_data"},
    )
    monkeypatch.setattr("scripts.refresh_market_data_r2._today_iso", lambda: "2026-01-05")
    rc = _run_main(monkeypatch, tmp_path, store)
    assert rc == 1
    artifact = json.loads((tmp_path / "refresh.json").read_text())
    assert artifact["stale"] is True
    by_ticker = {o["ticker"]: o for o in artifact["outcomes"]}
    assert by_ticker["SPY"]["mode"] == "incremental"
    assert by_ticker["BOOM"]["mode"] == "history-only"


def test_workflow_installs_uv_before_first_use() -> None:
    """`uv` is not on the GitHub runner; the job must set it up before running it (#4008)."""
    steps = _workflow()["jobs"]["refresh"]["steps"]
    uses = [str(step.get("uses", "")) for step in steps]
    assert any(u.startswith("astral-sh/setup-uv") for u in uses), "missing astral-sh/setup-uv"
    setup_index = next(i for i, u in enumerate(uses) if u.startswith("astral-sh/setup-uv"))
    first_uv_run = next(i for i, step in enumerate(steps) if "uv " in str(step.get("run", "")))
    assert setup_index < first_uv_run


def test_workflow_installs_the_prices_extra_for_yahoo_fetches() -> None:
    """refresh_market_data_r2.py imports yfinance from the `prices` extra (#4011)."""
    steps = _workflow()["jobs"]["refresh"]["steps"]
    sync = next(str(step["run"]) for step in steps if "uv sync" in str(step.get("run", "")))
    assert "--extra prices" in sync
    assert "--extra research" in sync
