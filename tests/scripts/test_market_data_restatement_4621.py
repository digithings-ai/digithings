"""Same-day market-data restatement via a new generation key (#4621).

Evening cron re-fetches the same ``as_of`` with different bytes. The base
generation key is immutable, so the refresh must seal the revision under a NEW
content-hash key and flip the ``latest`` pointer — never overwrite, never a
conflict-shaped ``error`` that trips the stale gate. Also pins the two
feasible follow-ups: PG registry rollback hygiene and the cadence-aware stale
gate (slow-macro history-only is benign; daily price failure still fails).
"""

from __future__ import annotations

import json
import sys
from pathlib import Path
from types import SimpleNamespace
from typing import Any

import polars as pl
import pytest

pytestmark = pytest.mark.unit

from digiquant.ops.checkpoint_archive import ArchiveVerifyError  # noqa: E402

import scripts.refresh_market_data_r2 as refresh_mod  # noqa: E402
from scripts.refresh_market_data_r2 import (  # noqa: E402
    FetchError,
    refresh_macro_series,
    refresh_ticker,
)

HIST = [
    ("2026-01-01", 100.0),
    ("2026-01-02", 101.0),
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
    """Refresh store double with real conflict semantics (same key + new bytes raise)."""

    def __init__(self) -> None:
        self.histories: dict[str, pl.DataFrame] = {}
        self.lives: dict[str, pl.DataFrame] = {}
        self.fulls: dict[str, pl.DataFrame] = {}
        self.macros: dict[tuple[str, str], list[dict]] = {}
        self.macro_lives: dict[tuple[str, str], list[dict]] = {}
        self.macro_empty: set[tuple[str, str]] = set()
        self.fetch_errors: dict[str, str] = {}
        self.always_conflict = False
        self.objects: dict[str, bytes] = {}
        self.puts: list[dict[str, Any]] = []
        self.pointers: dict[str, str] = {}
        self.manifest: dict[str, Any] = {"version": 1, "as_of": "2026-01-02", "datasets": {}}

    # -- read side ------------------------------------------------------
    def read_history(self, ticker: str) -> pl.DataFrame:
        try:
            return self.histories[ticker].clone()
        except KeyError:
            raise LookupError(f"unknown ticker {ticker!r}") from None

    def fetch_live(self, ticker: str, start: str, end: str) -> pl.DataFrame:
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
        frame = self.fulls.get(ticker)
        if frame is None:
            return price_frame(price_rows([], ticker)).clear()
        return frame.filter(pl.col("date") <= pl.lit(end).cast(pl.Date))

    def read_macro(self, source: str, series: str) -> pl.DataFrame:
        try:
            return pl.DataFrame(self.macros[(source, series)])
        except KeyError:
            raise LookupError(f"unknown macro {source}/{series}") from None

    def fetch_macro(self, source: str, series: str, start: str, end: str) -> list[dict]:
        if (source, series) in self.macro_empty:
            raise FetchError(f"{source}__{series}", "empty live window")
        return [
            r
            for r in self.macro_lives.get((source, series), [])
            if start <= str(r["obs_date"])[:10] <= end
        ]

    def fetch_macro_full(self, source: str, series: str, end: str) -> list[dict]:
        if (source, series) in self.macro_empty:
            raise FetchError(f"{source}__{series}", "empty full-window observations")
        return [
            r for r in self.macro_lives.get((source, series), []) if str(r["obs_date"])[:10] <= end
        ]

    # -- write side (mirrors the R2HistoryStore seam + dataset registration) --
    def put_generation(
        self,
        key: str,
        payload: bytes,
        source_table: str,
        source_key: dict[str, Any] | None = None,
        rows: int = -1,
    ) -> Any:
        import hashlib

        if self.always_conflict:
            raise ArchiveVerifyError(f"archive pointer conflict for {key}")
        if key in self.objects and self.objects[key] != payload:
            raise ArchiveVerifyError(f"archive pointer conflict for {key}")
        self.objects[key] = payload
        digest = hashlib.sha256(payload).hexdigest()
        self.puts.append({"key": key, "source_table": source_table, "rows": rows})
        info = dict(source_key or {})
        if source_table == "market-data/macro":
            dataset_id = f"{info.get('source')}__{info.get('series')}"
        else:
            dataset_id = str(info.get("ticker", key))
        self.manifest.setdefault("datasets", {})[dataset_id] = {
            "object": key,
            "sha256": digest,
            "rows": rows,
            "as_of": info.get("as_of", ""),
        }
        return SimpleNamespace(key=key, sha256=digest)

    def swap_latest_pointer(self, pointer_key: str, generation_key: str) -> None:
        self.pointers[pointer_key] = generation_key

    def write_manifest(self, manifest: dict[str, Any]) -> str:
        self.manifest = manifest
        return "fake"


BASE_PRICE_KEY = "market-data/price/SPY/2026-01-02.parquet"
PRICE_POINTER = "market-data/price/SPY/latest"


def _morning_seal(store: FakeStore) -> dict[str, Any]:
    """Morning run: bootstrap seals D1 under the base key."""
    store.fulls["SPY"] = price_frame(price_rows(HIST))
    return refresh_ticker("SPY", store, store.manifest, as_of="2026-01-02")


def test_morning_run_seals_base_key() -> None:
    store = FakeStore()
    outcome = _morning_seal(store)
    assert outcome["mode"] == "full-repull"
    assert outcome["as_of"] == "2026-01-02"
    assert store.pointers[PRICE_POINTER] == BASE_PRICE_KEY
    assert store.manifest["datasets"]["SPY"]["object"] == BASE_PRICE_KEY


def test_evening_restatement_seals_new_key_and_flips_pointer() -> None:
    """Morning-then-evening: same as_of, different bytes -> new key, no error."""
    store = FakeStore()
    _morning_seal(store)
    morning_bytes = store.objects[BASE_PRICE_KEY]

    revised = [("2026-01-01", 100.0), ("2026-01-02", 109.0)]
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(revised))
    store.fulls["SPY"] = price_frame(price_rows(revised))

    outcome = refresh_ticker("SPY", store, store.manifest, as_of="2026-01-02")
    assert outcome["mode"] == "full-repull"
    assert outcome["as_of"] == "2026-01-02"
    assert "same-day revision" in outcome["note"]
    new_key = store.pointers[PRICE_POINTER]
    assert new_key != BASE_PRICE_KEY
    assert new_key.startswith("market-data/price/SPY/2026-01-02--")
    assert new_key.endswith(".parquet")
    # Old generation untouched and still readable.
    assert store.objects[BASE_PRICE_KEY] == morning_bytes
    assert store.objects[new_key] != morning_bytes
    assert store.manifest["datasets"]["SPY"]["object"] == new_key


def test_evening_rerun_with_identical_bytes_is_up_to_date() -> None:
    """Re-running the evening bytes converges: no duplicate revision key."""
    store = FakeStore()
    _morning_seal(store)
    revised = [("2026-01-01", 100.0), ("2026-01-02", 109.0)]
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(revised))
    store.fulls["SPY"] = price_frame(price_rows(revised))
    first = refresh_ticker("SPY", store, store.manifest, as_of="2026-01-02")
    assert first["mode"] == "full-repull"
    puts_after_restatement = len(store.puts)

    store.histories["SPY"] = price_frame(price_rows(revised))
    second = refresh_ticker("SPY", store, store.manifest, as_of="2026-01-02")
    assert second["mode"] == "up-to-date"
    assert len(store.puts) == puts_after_restatement


def test_persistent_restatement_conflict_is_error_not_success() -> None:
    """A restatement put that itself conflicts stays a loud error (no greenwash)."""
    store = FakeStore()
    store.always_conflict = True
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows([("2026-01-01", 100.0), ("2026-01-02", 109.0)]))
    store.fulls["SPY"] = price_frame(price_rows([("2026-01-01", 100.0), ("2026-01-02", 109.0)]))
    outcome = refresh_ticker("SPY", store, store.manifest, as_of="2026-01-02")
    assert outcome["mode"] == "error"
    assert "conflict" in outcome["note"]
    assert store.pointers == {}


def test_macro_same_day_restatement_flips_pointer() -> None:
    hist = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 4.1},
    ]
    revised = [
        {"source": "fred", "series_id": "DGS10", "obs_date": "2026-01-02", "value": 9.9},
    ]
    store = FakeStore()
    # Morning seal under the base key via bootstrap (no history yet).
    store.macro_lives[("fred", "DGS10")] = hist
    morning = refresh_macro_series("fred", "DGS10", store, store.manifest, as_of="2026-01-02")
    assert morning["mode"] == "full-repull"
    base_key = "market-data/macro/fred__DGS10/2026-01-02.parquet"
    assert store.pointers["market-data/macro/fred__DGS10/latest"] == base_key
    morning_bytes = store.objects[base_key]

    # Evening: vendor revises the sealed print at the same obs_date.
    store.macros[("fred", "DGS10")] = hist
    store.macro_lives[("fred", "DGS10")] = revised
    outcome = refresh_macro_series("fred", "DGS10", store, store.manifest, as_of="2026-01-02")
    assert outcome["mode"] == "full-repull"
    assert outcome["as_of"] == "2026-01-02"
    assert "same-day revision" in outcome["note"]
    new_key = store.pointers["market-data/macro/fred__DGS10/latest"]
    assert new_key != base_key
    assert "--" in new_key
    assert store.objects[base_key] == morning_bytes


# -- PG registry hygiene ----------------------------------------------------


class _FakeCursor:
    def __init__(self, conn: "_FakeConn") -> None:
        self._conn = conn

    def execute(self, sql: str, params: tuple[Any, ...]) -> None:
        self._conn.statements.append((sql, params))
        if self._conn.fail_next:
            self._conn.fail_next = False
            raise RuntimeError("DuplicatePreparedStatement _pg3_0")

    def fetchall(self) -> list[tuple[Any, ...]]:
        return list(self._conn.rows)


class _FakeConn:
    def __init__(self) -> None:
        self.statements: list[tuple[str, tuple[Any, ...]]] = []
        self.rows: list[tuple[Any, ...]] = []
        self.rollbacks = 0
        self.commits = 0
        self.fail_next = False

    def cursor(self) -> _FakeCursor:
        return _FakeCursor(self)

    def commit(self) -> None:
        self.commits += 1

    def rollback(self) -> None:
        self.rollbacks += 1


def _holder(conn: _FakeConn) -> Any:
    return lambda uri: conn


def test_pg_insert_error_rolls_back_and_next_insert_succeeds() -> None:
    from scripts.backfill_market_data_r2 import _pg_registry_insert

    conn = _FakeConn()
    insert = _pg_registry_insert("postgresql://fake", connect=_holder(conn))
    conn.fail_next = True
    with pytest.raises(RuntimeError, match="DuplicatePreparedStatement"):
        insert("market-data/price", {"ticker": "SPY"}, "k1", "sha1", 10)
    assert conn.rollbacks == 1

    insert("market-data/price", {"ticker": "SPY"}, "k1", "sha1", 10)
    assert conn.commits == 1
    # Same-sha re-insert converges without a second commit.
    conn.rows = [("sha1",)]
    insert("market-data/price", {"ticker": "SPY"}, "k1", "sha1", 10)
    assert conn.commits == 1


def test_pg_lookup_error_rolls_back_and_reraises() -> None:
    from scripts.backfill_market_data_r2 import _pg_registry_lookup

    conn = _FakeConn()
    lookup = _pg_registry_lookup("postgresql://fake", connect=_holder(conn))
    conn.fail_next = True
    with pytest.raises(RuntimeError, match="DuplicatePreparedStatement"):
        lookup("k1")
    assert conn.rollbacks == 1
    assert lookup("missing") is None


def test_pg_connect_disables_server_prepares(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.backfill_market_data_r2 import _pg_connect

    seen: dict[str, Any] = {}

    class _Psycopg:
        @staticmethod
        def connect(uri: str, **kwargs: Any) -> str:
            seen.update(kwargs)
            return f"conn:{uri}"

    monkeypatch.setitem(sys.modules, "psycopg", _Psycopg())
    assert _pg_connect("postgresql://fake") == "conn:postgresql://fake"
    assert seen.get("prepare_threshold") is None


def test_pg_connect_falls_back_without_prepare_kwarg(monkeypatch: pytest.MonkeyPatch) -> None:
    from scripts.backfill_market_data_r2 import _pg_connect

    class _OldPsycopg:
        @staticmethod
        def connect(uri: str, **kwargs: Any) -> str:
            if "prepare_threshold" in kwargs:
                raise TypeError("unexpected kwarg")
            return f"plain:{uri}"

    monkeypatch.setitem(sys.modules, "psycopg", _OldPsycopg())
    assert _pg_connect("postgresql://fake") == "plain:postgresql://fake"


# -- cadence-aware stale gate -------------------------------------------------


def _run_main(
    monkeypatch: pytest.MonkeyPatch,
    tmp_path: Path,
    store: FakeStore,
    macro_specs: list[tuple[str, str, str | None]],
    run: str,
) -> tuple[int, dict[str, Any]]:
    store.manifest = {"version": 1, "as_of": run, "datasets": {}}
    monkeypatch.setattr(refresh_mod, "build_store", lambda uri: (store, store.manifest))
    monkeypatch.setattr(refresh_mod, "_resolve_macro_specs", lambda cli, path: macro_specs)
    rc = refresh_mod.main(
        [
            "--tickers",
            "SPY",
            "--postgres-uri",
            "postgresql://fake",
            "--manifest-out",
            str(tmp_path / "refresh.json"),
            "--as-of",
            run,
        ]
    )
    return rc, json.loads((tmp_path / "refresh.json").read_text())


def _slow_macro_store() -> FakeStore:
    store = FakeStore()
    store.histories["SPY"] = price_frame(price_rows(HIST))
    store.lives["SPY"] = price_frame(price_rows(HIST))
    store.macros[("fred", "PCEPI")] = [
        {"source": "fred", "series_id": "PCEPI", "obs_date": "2026-07-01", "value": 84.0},
    ]
    store.macro_empty.add(("fred", "PCEPI"))
    return store


def test_slow_macro_history_only_does_not_fail_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """A monthly FRED series sitting out its release cycle is quiet, not an outage."""
    rc, artifact = _run_main(
        monkeypatch, tmp_path, _slow_macro_store(), [("fred", "PCEPI", "monthly")], "2026-09-23"
    )
    assert rc == 0
    assert artifact["stale"] is False
    assert artifact["failed"] == []
    by_ticker = {o["ticker"]: o for o in artifact["outcomes"]}
    assert by_ticker["fred__PCEPI"]["mode"] == "history-only"


def test_daily_cadence_history_only_still_fails_run(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path
) -> None:
    """The exemption is cadence-scoped: a daily series with an empty window still fails."""
    rc, artifact = _run_main(
        monkeypatch, tmp_path, _slow_macro_store(), [("fred", "PCEPI", None)], "2026-09-23"
    )
    assert rc == 1
    assert artifact["stale"] is True
    assert artifact["failed"] == ["fred__PCEPI"]


def test_daily_price_error_still_fails_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Real feed death on a daily price ticker must still fail loud."""
    store = _slow_macro_store()
    store.fetch_errors["SPY"] = "no_data"
    rc, artifact = _run_main(
        monkeypatch, tmp_path, store, [("fred", "PCEPI", "monthly")], "2026-09-23"
    )
    assert rc == 1
    assert artifact["stale"] is True
    by_ticker = {o["ticker"]: o for o in artifact["outcomes"]}
    assert by_ticker["SPY"]["mode"] == "history-only"
    assert "SPY" in artifact["failed"]


def test_slow_macro_error_still_fails_run(monkeypatch: pytest.MonkeyPatch, tmp_path: Path) -> None:
    """Only history-only is exempt; a slow-series error is still loud."""
    store = _slow_macro_store()
    store.macro_empty.discard(("fred", "PCEPI"))
    store.macro_lives[("fred", "PCEPI")] = []

    def _boom(source: str, series: str, end: str) -> list[dict]:
        raise RuntimeError("fred down")

    store.fetch_macro_full = _boom  # type: ignore[method-assign]
    # Force the restatement path off and the error path on: empty history bootstrap
    # with a raising full fetch lands MODE_ERROR.
    del store.macros[("fred", "PCEPI")]
    rc, artifact = _run_main(
        monkeypatch, tmp_path, store, [("fred", "PCEPI", "monthly")], "2026-09-23"
    )
    assert rc == 1
    by_ticker = {o["ticker"]: o for o in artifact["outcomes"]}
    assert by_ticker["fred__PCEPI"]["mode"] == "error"
