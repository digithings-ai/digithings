"""Unit tests for the DigiQuant strategy store accessor (#1064)."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from typing import Any  # noqa: ANN401 — fake client mirrors the driver's dynamic surface

import polars as pl
import pytest

from digiquant.data.store import (
    PUBLIC_STRATEGY_COLUMNS,
    build_digiquant_client,
    digiquant_credentials,
    read_calibration,
    read_signals,
    read_strategies,
    record_trades,
    upsert_calibration,
    upsert_signal,
    upsert_strategies,
    upsert_tearsheet,
)
from digiquant.data.store.client import (
    CORE_SERVICE_KEY_ENV,
    CORE_URL_ENV,
    DIGIQUANT_SERVICE_ROLE_KEY_ENV,
    DIGIQUANT_URL_ENV,
    SUPABASE_SERVICE_ROLE_KEY_ENV,
    SUPABASE_URL_ENV,
)


# ─── Fake Supabase client (records selects; honors eq/limit; upsert/insert) ──────


@dataclass
class _Resp:
    data: list[dict[str, Any]]


@dataclass
class _Query:
    table_name: str
    store: dict[str, list[dict[str, Any]]]
    selects: list[str]
    _filters: list[tuple[str, Any]] = field(default_factory=list)
    _limit: int | None = None
    _pending: list[dict[str, Any]] | None = None
    _op: str | None = None

    def select(self, cols: str) -> "_Query":
        self.selects.append(cols)
        return self

    def eq(self, col: str, val: Any) -> "_Query":
        self._filters.append((col, val))
        return self

    def limit(self, n: int) -> "_Query":
        self._limit = n
        return self

    def upsert(self, row: Any) -> "_Query":
        rows = row if isinstance(row, list) else [row]
        self._pending = [dict(r) for r in rows]
        self._op = "upsert"
        return self

    def insert(self, rows: Any) -> "_Query":
        items = rows if isinstance(rows, list) else [rows]
        self._pending = [dict(r) for r in items]
        self._op = "insert"
        return self

    @staticmethod
    def _pk(row: dict[str, Any]) -> tuple[str, Any] | None:
        for key in ("strategy_id", "id"):
            if key in row:
                return key, row[key]
        return None

    def execute(self) -> _Resp:
        table = self.store.setdefault(self.table_name, [])
        if self._pending is not None:
            if self._op == "upsert":
                for row in self._pending:
                    pk = self._pk(row)
                    existing = (
                        next((r for r in table if r.get(pk[0]) == pk[1]), None) if pk else None
                    )
                    if existing is not None:
                        existing.update(row)
                    else:
                        table.append(row)
            else:  # insert
                table.extend(self._pending)
            return _Resp(data=list(self._pending))

        rows = [r for r in table if all(r.get(c) == v for c, v in self._filters)]
        if self._limit is not None:
            rows = rows[: self._limit]
        return _Resp(data=rows)


@dataclass
class FakeClient:
    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    selects: list[str] = field(default_factory=list)

    def table(self, name: str) -> _Query:
        return _Query(table_name=name, store=self.store, selects=self.selects)


# ─── Credentials / client factory ────────────────────────────────────────────────


@pytest.mark.unit
class TestCredentials:
    def _clear_all(self, mp: pytest.MonkeyPatch) -> None:
        for var in (
            CORE_URL_ENV,
            CORE_SERVICE_KEY_ENV,
            DIGIQUANT_URL_ENV,
            DIGIQUANT_SERVICE_ROLE_KEY_ENV,
            SUPABASE_URL_ENV,
            SUPABASE_SERVICE_ROLE_KEY_ENV,
        ):
            mp.delenv(var, raising=False)

    def test_core_vars_take_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """#1090: CORE_SUPABASE_* wins over the legacy _DIGIQUANT and SUPABASE_* names."""
        self._clear_all(monkeypatch)
        monkeypatch.setenv(SUPABASE_URL_ENV, "https://legacy.supabase.co")
        monkeypatch.setenv(SUPABASE_SERVICE_ROLE_KEY_ENV, "legacy-key")
        monkeypatch.setenv(DIGIQUANT_URL_ENV, "https://dq.supabase.co")
        monkeypatch.setenv(DIGIQUANT_SERVICE_ROLE_KEY_ENV, "dq-key")
        monkeypatch.setenv(CORE_URL_ENV, "https://core.supabase.co")
        monkeypatch.setenv(CORE_SERVICE_KEY_ENV, "core-key")
        assert digiquant_credentials() == ("https://core.supabase.co", "core-key")

    def test_digiquant_vars_used_when_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._clear_all(monkeypatch)
        monkeypatch.setenv(DIGIQUANT_URL_ENV, "https://dq.supabase.co")
        monkeypatch.setenv(DIGIQUANT_SERVICE_ROLE_KEY_ENV, "dq-key")
        assert digiquant_credentials() == ("https://dq.supabase.co", "dq-key")

    def test_falls_back_to_shared_supabase_vars(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """One project today: the store reuses SUPABASE_URL when _DIGIQUANT is unset."""
        self._clear_all(monkeypatch)
        monkeypatch.setenv(SUPABASE_URL_ENV, "https://core.supabase.co")
        monkeypatch.setenv(SUPABASE_SERVICE_ROLE_KEY_ENV, "core-key")
        assert digiquant_credentials() == ("https://core.supabase.co", "core-key")

    def test_digiquant_vars_take_precedence(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._clear_all(monkeypatch)
        monkeypatch.setenv(SUPABASE_URL_ENV, "https://core.supabase.co")
        monkeypatch.setenv(SUPABASE_SERVICE_ROLE_KEY_ENV, "core-key")
        monkeypatch.setenv(DIGIQUANT_URL_ENV, "https://dq.supabase.co")
        monkeypatch.setenv(DIGIQUANT_SERVICE_ROLE_KEY_ENV, "dq-key")
        assert digiquant_credentials() == ("https://dq.supabase.co", "dq-key")

    def test_blank_values_normalize_to_none(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._clear_all(monkeypatch)
        monkeypatch.setenv(DIGIQUANT_URL_ENV, "   ")
        assert digiquant_credentials() == (None, None)

    def test_build_client_returns_none_without_creds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        self._clear_all(monkeypatch)
        assert build_digiquant_client() is None


# ─── Strategies (public) ──────────────────────────────────────────────────────


@pytest.mark.unit
class TestStrategies:
    def test_upsert_then_read_roundtrip(self) -> None:
        client = FakeClient()
        upsert_strategies(
            client,
            [
                {"id": "slapper-btc", "symbol": "BTC-USD", "engine": "slapper", "enabled": True},
                {"id": "ema-eth", "symbol": "ETH-USD", "engine": "ema_cross", "enabled": False},
            ],
        )
        df = read_strategies(client)
        assert isinstance(df, pl.DataFrame)
        assert set(df["id"].to_list()) == {"slapper-btc", "ema-eth"}

    def test_read_enabled_only_filters(self) -> None:
        client = FakeClient()
        upsert_strategies(
            client,
            [
                {"id": "a", "symbol": "BTC-USD", "engine": "slapper", "enabled": True},
                {"id": "b", "symbol": "ETH-USD", "engine": "slapper", "enabled": False},
            ],
        )
        df = read_strategies(client, enabled_only=True)
        assert df["id"].to_list() == ["a"]

    def test_public_read_never_projects_calibration(self) -> None:
        """Security: the public strategies projection must not include calibration."""
        assert "calibration" not in PUBLIC_STRATEGY_COLUMNS
        client = FakeClient()
        read_strategies(client)
        # The select string handed to the client carries only non-sensitive columns.
        assert client.selects, "read_strategies must issue a projected select"
        assert all("calibration" not in sel for sel in client.selects)

    def test_empty_read_returns_empty_frame(self) -> None:
        df = read_strategies(FakeClient())
        assert isinstance(df, pl.DataFrame)
        assert df.height == 0


# ─── Calibrations (private sidecar) ────────────────────────────────────────────


@pytest.mark.unit
class TestCalibrations:
    def test_upsert_and_read_calibration(self) -> None:
        client = FakeClient()
        upsert_calibration(
            client, "slapper-btc", {"lookback": 20, "z": 1.5}, as_of=datetime(2026, 6, 25, 12)
        )
        assert read_calibration(client, "slapper-btc") == {"lookback": 20, "z": 1.5}

    def test_read_missing_calibration_is_none(self) -> None:
        assert read_calibration(FakeClient(), "nope") is None

    def test_calibration_written_to_private_table(self) -> None:
        client = FakeClient()
        upsert_calibration(client, "s1", {"k": 1})
        # Lands in the private sidecar, not on the public strategies table.
        assert "strategy_calibrations" in client.store
        assert "strategies" not in client.store


# ─── Signals / tearsheets / trades ─────────────────────────────────────────────


@pytest.mark.unit
class TestSignalsTearsheetsTrades:
    def test_upsert_signal_is_idempotent_per_strategy(self) -> None:
        client = FakeClient()
        upsert_signal(client, strategy_id="s1", position="long", as_of=datetime(2026, 6, 25))
        upsert_signal(
            client,
            strategy_id="s1",
            position="flat",
            as_of=datetime(2026, 6, 26),
            last_signal_date=date(2026, 6, 26),
            last_price=101.5,
        )
        df = read_signals(client)
        assert df.height == 1
        row = df.row(0, named=True)
        assert row["position"] == "flat"
        assert row["last_price"] == 101.5

    def test_upsert_tearsheet(self) -> None:
        client = FakeClient()
        upsert_tearsheet(
            client,
            strategy_id="s1",
            metrics={"sharpe": 1.2},
            as_of=datetime(2026, 6, 25),
            equity_curve=[1.0, 1.1],
        )
        stored = client.store["strategy_tearsheets"][0]
        assert stored["metrics"] == {"sharpe": 1.2}
        assert stored["equity_curve"] == [1.0, 1.1]

    def test_record_trades_appends_and_isoformats_timestamps(self) -> None:
        client = FakeClient()
        result = record_trades(
            client,
            [
                {
                    "strategy_id": "s1",
                    "entry_ts": datetime(2026, 6, 1, 9, 30),
                    "exit_ts": datetime(2026, 6, 2, 16, 0),
                    "side": "long",
                    "pnl": 12.0,
                }
            ],
        )
        assert result.rows == 1
        stored = client.store["strategy_trades"][0]
        assert stored["entry_ts"] == "2026-06-01T09:30:00"
        assert stored["exit_ts"] == "2026-06-02T16:00:00"

    def test_record_trades_empty_is_noop(self) -> None:
        client = FakeClient()
        assert record_trades(client, []).rows == 0
        assert client.store == {}
