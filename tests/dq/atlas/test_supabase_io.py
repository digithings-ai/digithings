"""Unit tests for digiquant.olympus.atlas.supabase_io — no live Supabase."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, timedelta
from typing import Any  # noqa: F401 — used for fake-client payload dict shape

import pytest

from digiquant.olympus.atlas.supabase_io import (
    SupabaseConfig,
    SupabaseNotConfiguredError,
    load_prior_context,
    publish_daily_snapshot,
    publish_document,
    query_macro_series_freshness,
    query_pending_decisions,
    query_price_deltas,
    query_price_technicals_freshness,
)


# ─── In-memory fake Supabase client ─────────────────────────────────────────


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]


@dataclass
class _FakeQuery:
    """Records calls and returns canned rows, honoring lt/gte/order/limit.

    The previous version of this fake made those methods no-ops, so tests
    that set ``desc=True`` or ``.limit(5)`` were validating Python list
    order, not real filter semantics. Now the fake actually applies them —
    so callers break loudly if the adapter forgets a filter.
    """

    table_name: str
    store: dict[str, list[dict[str, Any]]]
    canned: list[dict[str, Any]] = field(default_factory=list)
    _upsert_row: dict[str, Any] | None = None
    _update_row: dict[str, Any] | None = None
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _order: tuple[str, bool] | None = None
    _limit: int | None = None

    def select(self, _cols: str) -> "_FakeQuery":
        return self

    def lt(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("lt", col, val))
        return self

    def lte(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("lte", col, val))
        return self

    def gte(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("gte", col, val))
        return self

    def eq(self, col: str, val: Any) -> "_FakeQuery":
        self._filters.append(("eq", col, val))
        return self

    def in_(self, col: str, vals: list[Any] | tuple[Any, ...]) -> "_FakeQuery":
        # Match the Supabase Python client surface — ``in_`` filters rows whose
        # column value is one of ``vals``.
        self._filters.append(("in_", col, list(vals)))
        return self

    def order(self, col: str, desc: bool = False) -> "_FakeQuery":
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> "_FakeQuery":
        self._limit = n
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str | None = None) -> "_FakeQuery":
        self._upsert_row = dict(row)
        self._upsert_row["_on_conflict"] = on_conflict
        return self

    def update(self, payload: dict[str, Any]) -> "_FakeQuery":
        self._update_row = dict(payload)
        return self

    def execute(self) -> _FakeResponse:
        if self._upsert_row is not None:
            self.store.setdefault(self.table_name, []).append(self._upsert_row)
            return _FakeResponse(
                data=[{**self._upsert_row, "id": f"row-{len(self.store[self.table_name])}"}]
            )
        if self._update_row is not None:
            # Apply update to rows in store that match all eq filters. Mirrors
            # PostgREST's ``update().eq(...).execute()`` chain semantics so the
            # ``status='pending'`` idempotency guard in
            # ``update_decision_resolution`` is exercised end-to-end.
            updated: list[dict[str, Any]] = []
            for row in self.store.get(self.table_name, []):
                if all(
                    (op == "eq" and row.get(col) == val)
                    or (op == "lt" and str(row.get(col, "")) < str(val))
                    or (op == "lte" and str(row.get(col, "")) <= str(val))
                    or (op == "gte" and str(row.get(col, "")) >= str(val))
                    or (op == "in_" and row.get(col) in val)
                    for op, col, val in self._filters
                ):
                    row.update(self._update_row)
                    updated.append(row)
            return _FakeResponse(data=updated)
        rows = list(self.canned)
        for op, col, val in self._filters:
            if op == "lt":
                rows = [r for r in rows if str(r.get(col, "")) < str(val)]
            elif op == "lte":
                rows = [r for r in rows if str(r.get(col, "")) <= str(val)]
            elif op == "gte":
                rows = [r for r in rows if str(r.get(col, "")) >= str(val)]
            elif op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "in_":
                rows = [r for r in rows if r.get(col) in val]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows)


@dataclass
class FakeSupabaseClient:
    """Fake client with per-table canned-read state."""

    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    canned_reads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)

    def table(self, name: str) -> _FakeQuery:
        return _FakeQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
        )


# ─── Tests ──────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSupabaseConfig:
    def test_from_env_happy_path(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_ROLE_KEY", "sk-123")
        cfg = SupabaseConfig.from_env()
        assert cfg.url == "https://x.supabase.co"
        assert cfg.service_key == "sk-123"

    def test_from_env_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_ROLE_KEY", raising=False)
        with pytest.raises(SupabaseNotConfiguredError):
            SupabaseConfig.from_env()


@pytest.mark.unit
class TestPublishDocument:
    def test_idempotent_on_date_plus_document_key(self) -> None:
        client = FakeSupabaseClient()
        out1 = publish_document(
            client=client,
            document_key="macro/2026-04-20.json",
            payload={"regime": "slowing"},
            doc_type="macro",
            run_type="baseline",
            title="Macro 2026-04-20",
            date_str="2026-04-20",
        )
        out2 = publish_document(
            client=client,
            document_key="macro/2026-04-20.json",
            payload={"regime": "slowing"},
            doc_type="macro",
            run_type="baseline",
            title="Macro 2026-04-20",
            date_str="2026-04-20",
        )
        assert out1.table == "documents"
        assert out1.document_key == "macro/2026-04-20.json"
        # Both upserts record on_conflict on (date, document_key).
        rows = client.store["documents"]
        assert all(r["_on_conflict"] == "date,document_key" for r in rows)
        assert out2.document_key == out1.document_key

    def test_audit_redacts_nothing_unusual(self, caplog: pytest.LogCaptureFixture) -> None:
        """Happy-path audit line should contain the document_key (not a secret-bearing field)."""
        import logging

        client = FakeSupabaseClient()
        with caplog.at_level(logging.INFO, logger="digiquant.olympus.atlas.supabase_io"):
            publish_document(
                client=client,
                document_key="macro/2026-04-20.json",
                payload={"regime": "slowing"},
                doc_type="macro",
                run_type="baseline",
                title="t",
                date_str="2026-04-20",
            )
        audit_msgs = [r.message for r in caplog.records if "atlas_io audit" in r.message]
        assert audit_msgs, "expected an audit log line"
        assert "macro/2026-04-20.json" in audit_msgs[0]

    def test_audit_redacts_secret_bearing_keys(self, caplog: pytest.LogCaptureFixture) -> None:
        """If a caller inadvertently passed an api_key field via the outer
        audit payload it would be redacted. The adapter never puts secrets
        there today, but the contract must hold."""
        from digiquant.olympus.atlas.supabase_io import _audit

        import logging

        with caplog.at_level(logging.INFO, logger="digiquant.olympus.atlas.supabase_io"):
            _audit("test", {"document_key": "k", "api_key": "sk-should-not-appear"})
        msg = caplog.records[-1].message
        assert "sk-should-not-appear" not in msg
        assert "[REDACTED]" in msg


@pytest.mark.unit
class TestPublishDailySnapshot:
    def test_upsert_on_date(self) -> None:
        client = FakeSupabaseClient()
        out = publish_daily_snapshot(
            client=client,
            date_str="2026-04-20",
            snapshot={"regime": "slowing"},
            run_type="baseline",
            baseline_date=None,
        )
        assert out.table == "daily_snapshots"
        assert client.store["daily_snapshots"][0]["_on_conflict"] == "date"
        assert client.store["daily_snapshots"][0]["snapshot"] == {"regime": "slowing"}


@pytest.mark.unit
class TestLoadPriorContext:
    def test_documents_older_than_lookback_window_excluded(self) -> None:
        """Rows with dates before run_date - documents_lookback_days must be filtered."""
        # run_date = 2026-04-20; default lookback = 30 days → floor = 2026-03-21.
        docs = [
            {
                "date": "2026-04-10",  # inside window
                "document_key": "fresh/key.json",
                "doc_type": "macro",
                "payload": {"x": "new"},
            },
            {
                "date": "2026-02-01",  # far outside the 30-day window
                "document_key": "stale/key.json",
                "doc_type": "macro",
                "payload": {"x": "old"},
            },
        ]
        client = FakeSupabaseClient(canned_reads={"daily_snapshots": [], "documents": docs})
        ctx = load_prior_context(client=client, run_date=date(2026, 4, 20))
        assert "fresh/key.json" in ctx.latest_segments
        assert "stale/key.json" not in ctx.latest_segments

    def test_assembles_from_canned_rows(self) -> None:
        snapshots = [
            {"date": "2026-04-19", "run_type": "baseline", "snapshot": {"regime": "a"}},
            {"date": "2026-04-18", "run_type": "delta", "snapshot": {"regime": "b"}},
        ]
        docs = [
            {
                "date": "2026-04-19",
                "document_key": "macro/2026-04-19.json",
                "doc_type": "macro",
                "payload": {"regime": "a"},
            },
            {
                "date": "2026-04-19",
                "document_key": "thesis/2026-04-19.json",
                "doc_type": "thesis",
                "payload": {"label": "long-tech"},
            },
            # Older row for same macro key — latest-wins per document_key.
            {
                "date": "2026-04-18",
                "document_key": "macro/2026-04-19.json",
                "doc_type": "macro",
                "payload": {"regime": "stale"},
            },
        ]
        client = FakeSupabaseClient(canned_reads={"daily_snapshots": snapshots, "documents": docs})
        ctx = load_prior_context(client=client, run_date=date(2026, 4, 20))
        assert len(ctx.last_snapshots) == 2
        # Latest-per-key resolution kept the fresh macro row, not the stale one.
        assert ctx.latest_segments["macro/2026-04-19.json"]["payload"] == {"regime": "a"}
        # Thesis doc filtered into active_theses.
        assert any(t.get("label") == "long-tech" for t in ctx.active_theses)


@pytest.mark.unit
class TestDataLayerQueries:
    def test_price_technicals_freshness_empty(self) -> None:
        client = FakeSupabaseClient(canned_reads={"price_technicals": []})
        latest, count = query_price_technicals_freshness(client=client)
        assert latest is None
        assert count == 0

    def test_price_technicals_freshness_computes_max(self) -> None:
        rows = [
            {"date": "2026-04-18", "ticker": "SPY"},
            {"date": "2026-04-19", "ticker": "SPY"},
            {"date": "2026-04-19", "ticker": "QQQ"},
        ]
        client = FakeSupabaseClient(canned_reads={"price_technicals": rows})
        latest, count = query_price_technicals_freshness(client=client)
        assert latest == date(2026, 4, 19)
        assert count == 2  # distinct tickers

    def test_macro_series_freshness(self) -> None:
        rows = [{"obs_date": "2026-04-19"}]
        client = FakeSupabaseClient(canned_reads={"macro_series_observations": rows})
        assert query_macro_series_freshness(client=client) == date(2026, 4, 19)

    def test_macro_series_freshness_empty(self) -> None:
        client = FakeSupabaseClient(canned_reads={"macro_series_observations": []})
        assert query_macro_series_freshness(client=client) is None


@pytest.mark.unit
class TestQueryPriceDeltas:
    """Latest-two-trading-days pct_change calculation per ticker."""

    def test_empty_tickers_returns_empty(self) -> None:
        # No tickers requested → no DB roundtrip needed; empty dict.
        client = FakeSupabaseClient(canned_reads={"price_history": []})
        out = query_price_deltas(client=client, tickers=(), run_date=date(2026, 4, 27))
        assert out == {}

    def test_computes_pct_change_from_latest_two_trading_days(self) -> None:
        # SPY: 100 → 102 (+2%); TLT: 90 → 89.55 (-0.5%); QQQ has only one row.
        rows = [
            {"date": "2026-04-24", "ticker": "SPY", "close": 100.0},
            {"date": "2026-04-25", "ticker": "SPY", "close": 102.0},
            {"date": "2026-04-24", "ticker": "TLT", "close": 90.0},
            {"date": "2026-04-25", "ticker": "TLT", "close": 89.55},
            {"date": "2026-04-25", "ticker": "QQQ", "close": 400.0},
        ]
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = query_price_deltas(
            client=client,
            tickers=("SPY", "TLT", "QQQ"),
            run_date=date(2026, 4, 27),
        )
        assert out["SPY"] == pytest.approx(0.02)
        assert out["TLT"] == pytest.approx(-0.005)
        # QQQ has only one row → silently dropped (caller treats as no signal).
        assert "QQQ" not in out

    def test_skips_weekend_gaps_correctly(self) -> None:
        """Run date Monday — query must look at Fri vs Thu, not Sun vs Sat."""
        # Wed/Thu/Fri prices; Mon run date should pick Thu→Fri (latest pair
        # of distinct trading days strictly before Mon).
        rows = [
            {"date": "2026-04-22", "ticker": "GLD", "close": 200.0},  # Wed
            {"date": "2026-04-23", "ticker": "GLD", "close": 201.0},  # Thu
            {"date": "2026-04-24", "ticker": "GLD", "close": 203.01},  # Fri
        ]
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = query_price_deltas(
            client=client,
            tickers=("GLD",),
            run_date=date(2026, 4, 27),  # Mon
        )
        assert "GLD" in out
        # Latest two are Fri/Thu: (203.01 - 201.0) / 201.0 ≈ 0.01000 (1.00%).
        assert out["GLD"] == pytest.approx(0.01, abs=1e-4)

    def test_excludes_rows_at_or_after_run_date(self) -> None:
        """The lookup must NOT include the run-date row itself — the
        triage decision is about regenerating *today's* analysis vs
        carrying yesterday's; the price-delta is `(yesterday - day_before).`"""
        rows = [
            {"date": "2026-04-25", "ticker": "SPY", "close": 100.0},
            {"date": "2026-04-26", "ticker": "SPY", "close": 110.0},
            # This row would mask the 100→110 move if it leaked in.
            {"date": "2026-04-27", "ticker": "SPY", "close": 110.5},
        ]
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = query_price_deltas(
            client=client,
            tickers=("SPY",),
            run_date=date(2026, 4, 27),
        )
        assert out["SPY"] == pytest.approx(0.10)

    def test_handles_string_close_values(self) -> None:
        """Postgres numeric columns sometimes surface as strings via PostgREST."""
        rows = [
            {"date": "2026-04-24", "ticker": "TLT", "close": "90.0"},
            {"date": "2026-04-25", "ticker": "TLT", "close": "90.9"},
        ]
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = query_price_deltas(
            client=client,
            tickers=("TLT",),
            run_date=date(2026, 4, 26),
        )
        assert out["TLT"] == pytest.approx(0.01)

    def test_zero_prior_close_is_dropped(self) -> None:
        # A division-by-zero guard — never raise, just drop the ticker.
        rows = [
            {"date": "2026-04-24", "ticker": "BIL", "close": 0.0},
            {"date": "2026-04-25", "ticker": "BIL", "close": 91.5},
        ]
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = query_price_deltas(
            client=client,
            tickers=("BIL",),
            run_date=date(2026, 4, 27),
        )
        assert out == {}

    def test_filters_request_to_requested_tickers(self) -> None:
        """The .in_ filter must keep us from pulling rows for unrelated
        tickers — protects the rule engine from receiving unexpected keys."""
        rows = [
            {"date": "2026-04-24", "ticker": "SPY", "close": 100.0},
            {"date": "2026-04-25", "ticker": "SPY", "close": 101.0},
            {"date": "2026-04-24", "ticker": "QQQ", "close": 400.0},
            {"date": "2026-04-25", "ticker": "QQQ", "close": 408.0},
        ]
        client = FakeSupabaseClient(canned_reads={"price_history": rows})
        out = query_price_deltas(
            client=client,
            tickers=("SPY",),
            run_date=date(2026, 4, 27),
        )
        assert "QQQ" not in out
        assert "SPY" in out


@pytest.mark.unit
class TestQueryPendingDueWindow:
    """Pillar 3A — the due-window lower bound is inclusive (``<=``): a decision dated exactly
    run_date − holding_days_default is due today and must be returned (``<`` dropped it)."""

    def _row(self, run_date_iso: str, ticker: str = "AAPL") -> dict:
        return {
            "id": f"d-{ticker}-{run_date_iso}",
            "run_id": "run-1",
            "run_date": run_date_iso,
            "ticker": ticker,
            "stance": "buy",
            "conviction": 4,
            "thesis": "t",
            "benchmark": "SPY",
            "holding_days": 5,
            "status": "pending",
        }

    def test_boundary_run_date_is_due(self) -> None:
        run_date = date(2026, 6, 20)
        floor = (
            run_date - timedelta(days=5)
        ).isoformat()  # exactly run_date − holding_days_default
        client = FakeSupabaseClient(canned_reads={"decision_log": [self._row(floor)]})
        due = query_pending_decisions(client=client, run_date=run_date)
        assert [d["id"] for d in due] == [self._row(floor)["id"]]  # boundary included

    def test_future_decision_not_due(self) -> None:
        run_date = date(2026, 6, 20)
        too_recent = (run_date - timedelta(days=2)).isoformat()  # window not yet elapsed
        client = FakeSupabaseClient(canned_reads={"decision_log": [self._row(too_recent)]})
        assert query_pending_decisions(client=client, run_date=run_date) == []
