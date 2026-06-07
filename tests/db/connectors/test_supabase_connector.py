"""Unit tests for SupabaseConnector — the supabase client is faked, no live DB.

Mirrors ``tests/db/connectors/test_notion_connector.py`` (typed-result
assertions, success/failure paths) and reuses the in-memory fake-client shape
from ``tests/dq/atlas/test_supabase_io.py`` (records calls, honours filters).

The connector is imported directly from the submodule rather than via the
``digibase.connectors`` package: the package ``__init__`` export for
``SupabaseConnector`` is added by the integrator, so a package-attribute import
would be premature here.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any

import pytest

from digibase.connectors.supabase import (
    SupabaseConnector,
    SupabaseNotConfiguredError,
    SupabaseReadResult,
    SupabaseWriteResult,
)

pytestmark = pytest.mark.unit


# ─── In-memory fake Supabase client ─────────────────────────────────────────


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]
    count: int | None = None


@dataclass
class _FakeQuery:
    """Records calls and returns canned rows, honouring eq/gte/lte/in_/order/limit.

    Filters are applied for real (not no-ops) so a connector that forgets a
    filter breaks loudly — same philosophy as the Atlas supabase_io fake.
    """

    table_name: str
    store: dict[str, list[dict[str, Any]]]
    canned: list[dict[str, Any]] = field(default_factory=list)
    raise_on_execute: Exception | None = None
    _upsert_rows: list[dict[str, Any]] | None = None
    _on_conflict: str | None = None
    _on_conflict_passed: bool = False
    _count_mode: str | None = None
    _filters: list[tuple[str, str, Any]] = field(default_factory=list)
    _order: tuple[str, bool] | None = None
    _limit: int | None = None
    calls: dict[str, Any] = field(default_factory=dict)

    def select(self, cols: str, count: str | None = None) -> _FakeQuery:
        self.calls["select_cols"] = cols
        self._count_mode = count
        return self

    def eq(self, col: str, val: Any) -> _FakeQuery:
        self._filters.append(("eq", col, val))
        return self

    def gte(self, col: str, val: Any) -> _FakeQuery:
        self._filters.append(("gte", col, val))
        return self

    def lte(self, col: str, val: Any) -> _FakeQuery:
        self._filters.append(("lte", col, val))
        return self

    def in_(self, col: str, vals: list[Any] | tuple[Any, ...]) -> _FakeQuery:
        self._filters.append(("in_", col, list(vals)))
        return self

    def order(self, col: str, desc: bool = False) -> _FakeQuery:
        self._order = (col, desc)
        return self

    def limit(self, n: int) -> _FakeQuery:
        self._limit = n
        return self

    def upsert(self, rows: list[dict[str, Any]], **kwargs: Any) -> _FakeQuery:
        # Mirror the real client: ``on_conflict`` is keyword-only. The connector
        # omits the kwarg entirely for a no-conflict upsert, so we record whether
        # it was supplied at all (not just its value).
        self._upsert_rows = [dict(r) for r in rows]
        self._on_conflict_passed = "on_conflict" in kwargs
        self._on_conflict = kwargs.get("on_conflict")
        return self

    def execute(self) -> _FakeResponse:
        if self.raise_on_execute is not None:
            raise self.raise_on_execute
        if self._upsert_rows is not None:
            stored = self.store.setdefault(self.table_name, [])
            for row in self._upsert_rows:
                stored.append({**row, "_on_conflict": self._on_conflict})
            return _FakeResponse(data=list(self._upsert_rows))
        rows = list(self.canned)
        for op, col, val in self._filters:
            if op == "eq":
                rows = [r for r in rows if r.get(col) == val]
            elif op == "gte":
                rows = [r for r in rows if str(r.get(col, "")) >= str(val)]
            elif op == "lte":
                rows = [r for r in rows if str(r.get(col, "")) <= str(val)]
            elif op == "in_":
                rows = [r for r in rows if r.get(col) in val]
        if self._order is not None:
            col, desc = self._order
            rows.sort(key=lambda r: r.get(col, ""), reverse=desc)
        count = len(rows) if self._count_mode else None
        if self._limit is not None:
            rows = rows[: self._limit]
        return _FakeResponse(data=rows, count=count)


@dataclass
class FakeSupabaseClient:
    """Fake client with per-table canned-read state and recorded queries."""

    store: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    canned_reads: dict[str, list[dict[str, Any]]] = field(default_factory=dict)
    raise_on_execute: Exception | None = None
    last_query: _FakeQuery | None = None

    def table(self, name: str) -> _FakeQuery:
        query = _FakeQuery(
            table_name=name,
            store=self.store,
            canned=list(self.canned_reads.get(name, [])),
            raise_on_execute=self.raise_on_execute,
        )
        self.last_query = query
        return query


# ─── from_env ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestFromEnv:
    def test_missing_both_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        with pytest.raises(SupabaseNotConfiguredError) as exc:
            SupabaseConnector.from_env()
        assert "SUPABASE_URL" in str(exc.value)
        assert "SUPABASE_SERVICE_KEY" in str(exc.value)

    def test_missing_key_only_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
        with pytest.raises(SupabaseNotConfiguredError) as exc:
            SupabaseConnector.from_env()
        assert "SUPABASE_SERVICE_KEY" in str(exc.value)
        assert "SUPABASE_URL" not in str(exc.value)

    def test_calls_create_client_with_resolved_creds(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """from_env defers the supabase import and forwards url + key.

        We stub a fake ``supabase`` module so the real package (and any network)
        is never touched — this is what proves the import is deferred, not
        top-level.
        """
        import sys
        import types

        captured: dict[str, Any] = {}
        fake_module = types.ModuleType("supabase")

        def _create_client(url: str, key: str) -> str:
            captured["url"] = url
            captured["key"] = key
            return "fake-client"

        fake_module.create_client = _create_client  # type: ignore[attr-defined]
        monkeypatch.setitem(sys.modules, "supabase", fake_module)
        monkeypatch.setenv("SUPABASE_URL", "https://x.supabase.co")
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sk-123")

        connector = SupabaseConnector.from_env()
        assert captured == {"url": "https://x.supabase.co", "key": "sk-123"}
        assert connector.client == "fake-client"

    def test_custom_env_var_names(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.setenv("MY_URL", "https://y.supabase.co")
        monkeypatch.delenv("MY_KEY", raising=False)
        with pytest.raises(SupabaseNotConfiguredError) as exc:
            SupabaseConnector.from_env(url_var="MY_URL", key_var="MY_KEY")
        assert "MY_KEY" in str(exc.value)
        assert "MY_URL" not in str(exc.value)


# ─── upsert ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestUpsert:
    def test_single_row_with_on_conflict(self) -> None:
        client = FakeSupabaseClient()
        connector = SupabaseConnector(client)
        out = connector.upsert(
            "fx_research_history_v2",
            {"file_id": "123", "run_date": "2026-06-07", "broker_name": "GS"},
            on_conflict="file_id,run_date",
        )
        assert isinstance(out, SupabaseWriteResult)
        assert out.success is True
        assert out.table == "fx_research_history_v2"
        assert out.rows == 1
        stored = client.store["fx_research_history_v2"]
        assert stored[0]["_on_conflict"] == "file_id,run_date"
        assert stored[0]["broker_name"] == "GS"

    def test_without_on_conflict_omits_the_kwarg(self) -> None:
        """A no-conflict upsert must call ``.upsert(rows)`` with no ``on_conflict``
        kwarg — byte-identical to the bare form used in production (e.g.
        digiquant price_history writes), not ``on_conflict=None``.
        """
        client = FakeSupabaseClient()
        connector = SupabaseConnector(client)
        out = connector.upsert("price_history", [{"date": "2026-06-07", "close": 1.0}])
        assert out.success is True
        assert out.rows == 1
        assert client.last_query is not None
        assert client.last_query._on_conflict_passed is False
        assert client.store["price_history"][0]["_on_conflict"] is None

    def test_list_of_rows(self) -> None:
        client = FakeSupabaseClient()
        connector = SupabaseConnector(client)
        rows = [{"external_id": f"e{i}"} for i in range(3)]
        out = connector.upsert("fx_economic_calendar", rows, on_conflict="external_id")
        assert out.success is True
        assert out.rows == 3
        assert len(client.store["fx_economic_calendar"]) == 3

    def test_empty_list_is_noop_success(self) -> None:
        client = FakeSupabaseClient()
        connector = SupabaseConnector(client)
        out = connector.upsert("t", [])
        assert out.success is True
        assert out.rows == 0
        assert "t" not in client.store  # no roundtrip

    def test_chunks_large_batches(self) -> None:
        """Rows beyond ``chunk`` are sent in multiple requests; count is total."""
        client = FakeSupabaseClient()
        connector = SupabaseConnector(client)
        rows = [{"external_id": f"e{i}"} for i in range(250)]
        out = connector.upsert("t", rows, on_conflict="external_id", chunk=100)
        assert out.success is True
        assert out.rows == 250
        # All 250 landed despite 3 batched requests (100 + 100 + 50).
        assert len(client.store["t"]) == 250

    def test_failure_is_caught_and_returned(self) -> None:
        client = FakeSupabaseClient(raise_on_execute=RuntimeError("pgrst timeout"))
        connector = SupabaseConnector(client)
        out = connector.upsert("t", {"a": 1}, on_conflict="a")
        assert out.success is False
        assert "pgrst timeout" in out.error
        assert out.rows == 0

    def test_audit_emits_metadata_only(self, caplog: pytest.LogCaptureFixture) -> None:
        """Audit line carries table/operation/rows/on_conflict — never row bodies."""
        import logging

        client = FakeSupabaseClient()
        connector = SupabaseConnector(client)
        with caplog.at_level(logging.INFO, logger="digibase.connectors.supabase"):
            connector.upsert(
                "secrets_table",
                {"api_key": "sk-super-secret", "row_value": "pii-data"},
                on_conflict="id",
            )
        audit_msgs = [r.message for r in caplog.records if "supabase audit" in r.message]
        assert audit_msgs, "expected an audit log line"
        msg = audit_msgs[0]
        # Metadata present.
        assert "secrets_table" in msg
        assert "upsert" in msg
        assert "id" in msg
        # Row body values are never audited.
        assert "sk-super-secret" not in msg
        assert "pii-data" not in msg


# ─── select ────────────────────────────────────────────────────────────────


@pytest.mark.unit
class TestSelect:
    def test_select_all_no_filters(self) -> None:
        rows = [{"run_date": "2026-06-01"}, {"run_date": "2026-06-02"}]
        client = FakeSupabaseClient(canned_reads={"fx_research_history_v2": rows})
        connector = SupabaseConnector(client)
        out = connector.select("fx_research_history_v2")
        assert isinstance(out, SupabaseReadResult)
        assert out.success is True
        assert out.rows == rows
        assert out.count is None

    def test_eq_filter(self) -> None:
        rows = [
            {"run_date": "2026-06-01", "broker_name": "GS"},
            {"run_date": "2026-06-01", "broker_name": "DB"},
        ]
        client = FakeSupabaseClient(canned_reads={"t": rows})
        connector = SupabaseConnector(client)
        out = connector.select("t", eq={"broker_name": "GS"})
        assert [r["broker_name"] for r in out.rows] == ["GS"]

    def test_gte_filter(self) -> None:
        rows = [
            {"run_date": "2026-05-30"},
            {"run_date": "2026-06-01"},
            {"run_date": "2026-06-05"},
        ]
        client = FakeSupabaseClient(canned_reads={"t": rows})
        connector = SupabaseConnector(client)
        out = connector.select("t", gte={"run_date": "2026-06-01"})
        assert {r["run_date"] for r in out.rows} == {"2026-06-01", "2026-06-05"}

    def test_lte_and_gte_window(self) -> None:
        rows = [{"event_date": d} for d in ("2026-06-01", "2026-06-10", "2026-06-20")]
        client = FakeSupabaseClient(canned_reads={"fx_economic_calendar": rows})
        connector = SupabaseConnector(client)
        out = connector.select(
            "fx_economic_calendar",
            gte={"event_date": "2026-06-05"},
            lte={"event_date": "2026-06-15"},
        )
        assert [r["event_date"] for r in out.rows] == ["2026-06-10"]

    def test_in_filter(self) -> None:
        rows = [{"country": c} for c in ("US", "EU", "JP")]
        client = FakeSupabaseClient(canned_reads={"t": rows})
        connector = SupabaseConnector(client)
        out = connector.select("t", in_={"country": ["US", "JP"]})
        assert {r["country"] for r in out.rows} == {"US", "JP"}

    def test_order_desc_and_limit(self) -> None:
        rows = [{"d": "2026-06-01"}, {"d": "2026-06-03"}, {"d": "2026-06-02"}]
        client = FakeSupabaseClient(canned_reads={"t": rows})
        connector = SupabaseConnector(client)
        out = connector.select("t", order="d", desc=True, limit=2)
        assert [r["d"] for r in out.rows] == ["2026-06-03", "2026-06-02"]

    def test_count_populates_result(self) -> None:
        rows = [{"id": 1}, {"id": 2}, {"id": 3}]
        client = FakeSupabaseClient(canned_reads={"t": rows})
        connector = SupabaseConnector(client)
        out = connector.select("t", columns="id", count="exact", limit=1)
        assert out.count == 3  # full count, independent of limit
        assert len(out.rows) == 1

    def test_columns_forwarded(self) -> None:
        client = FakeSupabaseClient(canned_reads={"t": [{"run_date": "x"}]})
        connector = SupabaseConnector(client)
        connector.select("t", columns="run_date")
        assert client.last_query is not None
        assert client.last_query.calls["select_cols"] == "run_date"

    def test_empty_data_returns_empty_list(self) -> None:
        client = FakeSupabaseClient(canned_reads={})
        connector = SupabaseConnector(client)
        out = connector.select("t", eq={"x": "y"})
        assert out.success is True
        assert out.rows == []

    def test_failure_is_caught_and_returned(self) -> None:
        client = FakeSupabaseClient(raise_on_execute=ValueError("bad filter"))
        connector = SupabaseConnector(client)
        out = connector.select("t", eq={"x": 1})
        assert out.success is False
        assert "bad filter" in out.error
        assert out.rows == []
