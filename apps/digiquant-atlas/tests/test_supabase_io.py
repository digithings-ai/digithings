"""Unit tests for digiquant_atlas.supabase_io — no live Supabase."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from typing import Any  # noqa: F401 — used for fake-client payload dict shape

import pytest

from digiquant_atlas.supabase_io import (
    SupabaseConfig,
    SupabaseNotConfiguredError,
    load_prior_context,
    publish_daily_snapshot,
    publish_document,
    query_macro_series_freshness,
    query_price_technicals_freshness,
)


# ─── In-memory fake Supabase client ─────────────────────────────────────────


@dataclass
class _FakeResponse:
    data: list[dict[str, Any]]


@dataclass
class _FakeQuery:
    """Records calls and returns canned rows.

    Supports the chained shape our adapter uses:
        client.table("x").upsert(row, on_conflict="...").execute()
        client.table("x").select("...").lt(...).order(...).limit(...).execute()
    """

    table_name: str
    store: dict[str, list[dict[str, Any]]]
    canned: list[dict[str, Any]] = field(default_factory=list)
    _upsert_row: dict[str, Any] | None = None

    def select(self, _cols: str) -> "_FakeQuery":
        return self

    def lt(self, _col: str, _val: Any) -> "_FakeQuery":
        return self

    def eq(self, _col: str, _val: Any) -> "_FakeQuery":
        return self

    def order(self, _col: str, desc: bool = False) -> "_FakeQuery":
        return self

    def limit(self, _n: int) -> "_FakeQuery":
        return self

    def upsert(self, row: dict[str, Any], on_conflict: str | None = None) -> "_FakeQuery":
        self._upsert_row = dict(row)
        self._upsert_row["_on_conflict"] = on_conflict
        return self

    def execute(self) -> _FakeResponse:
        if self._upsert_row is not None:
            self.store.setdefault(self.table_name, []).append(self._upsert_row)
            return _FakeResponse(
                data=[{**self._upsert_row, "id": f"row-{len(self.store[self.table_name])}"}]
            )
        return _FakeResponse(data=list(self.canned))


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
        monkeypatch.setenv("SUPABASE_SERVICE_KEY", "sk-123")
        cfg = SupabaseConfig.from_env()
        assert cfg.url == "https://x.supabase.co"
        assert cfg.service_key == "sk-123"

    def test_from_env_missing_raises(self, monkeypatch: pytest.MonkeyPatch) -> None:
        monkeypatch.delenv("SUPABASE_URL", raising=False)
        monkeypatch.delenv("SUPABASE_SERVICE_KEY", raising=False)
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
        with caplog.at_level(logging.INFO, logger="digiquant_atlas.supabase_io"):
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
        from digiquant_atlas.supabase_io import _audit

        import logging

        with caplog.at_level(logging.INFO, logger="digiquant_atlas.supabase_io"):
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
        rows = [{"date": "2026-04-19"}]
        client = FakeSupabaseClient(canned_reads={"macro_series_observations": rows})
        assert query_macro_series_freshness(client=client) == date(2026, 4, 19)

    def test_macro_series_freshness_empty(self) -> None:
        client = FakeSupabaseClient(canned_reads={"macro_series_observations": []})
        assert query_macro_series_freshness(client=client) is None
