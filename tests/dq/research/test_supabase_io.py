"""Unit tests for digiquant.research.supabase_io — no live Supabase."""

from __future__ import annotations

import json
import logging
from datetime import date, datetime, timedelta
from uuid import UUID, uuid4

import pytest
from digiquant.research.supabase_io import (
    _DEFAULT_PRICE_LOOKBACK_DAYS,
    SupabaseConfig,
    SupabaseNotConfiguredError,
    _json_safe,
    _price_delta_ticker_batch,
    load_active_theses_rows,
    load_portfolio_performance_snapshot,
    load_prior_analyst_summaries,
    load_prior_book,
    load_prior_context,
    load_prior_deliberation_summaries,
    prior_book_current_weights,
    publish_daily_snapshot,
    publish_document,
    query_macro_series_freshness,
    query_pending_decisions,
    query_price_deltas,
    query_price_technicals_freshness,
    upsert_onchain_cohort_positioning,
)
from digiquant.dashboard.tenancy import house_workspace_id

# Canonical fake lives in tests.fixtures.fake_supabase (#1196); re-export so
# existing ``from tests.dq.atlas.test_supabase_io import FakeSupabaseClient``
# imports keep working.
from tests.fixtures.fake_supabase import (
    FakeSupabaseClient as FakeSupabaseClient,
)
from tests.fixtures.fake_supabase import (
    _FakeQuery as _FakeQuery,
)
from tests.fixtures.fake_supabase import (
    _FakeResponse as _FakeResponse,
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
class TestJsonSafe:
    """`_json_safe` is the write-boundary coercion that keeps date/datetime
    and UUID objects out of the JSON body the Supabase client hands to httpx."""

    def test_coerces_date_and_datetime_recursively(self) -> None:
        out = _json_safe(
            {
                "date": date(2026, 6, 22),
                "roster": [{"as_of": datetime(2026, 6, 22, 13, 30)}, "flat"],
                "label": "long-tech",
                "rank": 3,
                "weight": None,
            }
        )
        assert out == {
            "date": "2026-06-22",
            "roster": [{"as_of": "2026-06-22T13:30:00"}, "flat"],
            "label": "long-tech",
            "rank": 3,
            "weight": None,
        }
        json.dumps(out)  # the whole structure must be JSON-encodable

    def test_coerces_uuid_recursively(self) -> None:
        """Regression (house GHA 33426508863 retry): checkpoint-rehydrated
        payloads carry raw ``UUID``. Port of main [#3334](https://github.com/digithings-ai/digithings/pull/3334)."""
        ws = UUID("6b753576-ced9-5319-9bfa-c5d0aacd9319")
        out = _json_safe(
            {
                "workspace_id": ws,
                "nested": [{"commit_id": ws}],
                "label": "house",
            }
        )
        assert out == {
            "workspace_id": "6b753576-ced9-5319-9bfa-c5d0aacd9319",
            "nested": [{"commit_id": "6b753576-ced9-5319-9bfa-c5d0aacd9319"}],
            "label": "house",
        }
        json.dumps(out)


@pytest.mark.unit
class TestPublishDocument:
    def test_serializes_date_objects_nested_in_payload(self) -> None:
        """Regression (Olympus daily crash, 2026-06-22): a ``PMDirectionMemo``
        rehydrated from a LangGraph checkpoint as a plain dict — rather than the
        Pydantic model — carries a raw ``datetime.date`` in ``payload['date']``.
        The Supabase client JSON-encodes the row via httpx, so the date must be
        coerced to an ISO string before upsert or it raises
        ``TypeError: Object of type date is not JSON serializable``."""
        client = FakeSupabaseClient()
        publish_document(
            client=client,
            document_key="pm-direction-memo",
            payload={"schema_version": "1.0", "date": date(2026, 6, 22), "roster": []},
            doc_type="PM Direction Memo",
            run_type="baseline",
            title="PM Direction 2026-06-22",
            date_str="2026-06-22",
            category="portfolio",
        )
        row = client.store["documents"][0]
        json.dumps(row)  # mirrors the real client's encode step — must not raise
        assert row["payload"]["date"] == "2026-06-22"

    def test_serializes_uuid_objects_nested_in_payload(self) -> None:
        """Regression (house GHA 33426508863): H9 ``publish_document`` retry
        died in httpx on a nested UUID. Port of main #3334."""
        client = FakeSupabaseClient()
        ws = UUID("6b753576-ced9-5319-9bfa-c5d0aacd9319")
        publish_document(
            client=client,
            document_key="analyst/SPY",
            payload={"workspace_id": ws, "ticker": "SPY"},
            doc_type=None,
            run_type="delta",
            title="SPY analyst 2026-08-31",
            date_str="2026-08-31",
            category="deep-dive",
            segment="analyst",
            sector="SPY",
        )
        row = client.store["documents"][0]
        json.dumps(row)
        assert row["payload"]["workspace_id"] == "6b753576-ced9-5319-9bfa-c5d0aacd9319"

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
        # Both upserts record on_conflict on (workspace_id, date, document_key).
        rows = client.store["documents"]
        assert all(r["_on_conflict"] == "workspace_id,date,document_key" for r in rows)
        assert all(r["workspace_id"] == str(house_workspace_id()) for r in rows)
        assert out2.document_key == out1.document_key

    def test_audit_redacts_nothing_unusual(self, caplog: pytest.LogCaptureFixture) -> None:
        """Happy-path audit line should contain the document_key (not a secret-bearing field)."""
        import logging

        client = FakeSupabaseClient()
        with caplog.at_level(logging.INFO, logger="digiquant.research.supabase_io"):
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
        import logging

        from digiquant.research.supabase_io import _audit

        with caplog.at_level(logging.INFO, logger="digiquant.research.supabase_io"):
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

    def test_serializes_date_objects_in_snapshot(self) -> None:
        """Same date-not-serializable class as documents — the snapshot JSONB
        payload is written in the same H9 commit step."""
        client = FakeSupabaseClient()
        publish_daily_snapshot(
            client=client,
            date_str="2026-06-22",
            snapshot={"regime": "slowing", "as_of": date(2026, 6, 22)},
            run_type="baseline",
            baseline_date=None,
        )
        row = client.store["daily_snapshots"][0]
        json.dumps(row)  # must not raise
        assert row["snapshot"]["as_of"] == "2026-06-22"

    def test_refuses_overlay_workspace(self) -> None:
        client = FakeSupabaseClient()
        with pytest.raises(ValueError, match="house digest table"):
            publish_daily_snapshot(
                client=client,
                date_str="2026-08-31",
                snapshot={"regime": "overlay"},
                run_type="baseline",
                workspace_id=str(uuid4()),
            )
        assert client.store.get("daily_snapshots", []) == []

    def test_house_workspace_id_still_upserts(self) -> None:
        client = FakeSupabaseClient()
        publish_daily_snapshot(
            client=client,
            date_str="2026-08-31",
            snapshot={"regime": "house"},
            run_type="baseline",
            workspace_id=str(house_workspace_id()),
        )
        assert len(client.store["daily_snapshots"]) == 1


@pytest.mark.unit
class TestUpsertOnchainCohortPositioning:
    def test_serializes_date_objects_in_rows(self) -> None:
        """Every write through this adapter must survive JSON encoding — a
        date-bearing on-chain row would otherwise crash the upsert too."""
        client = FakeSupabaseClient()
        written = upsert_onchain_cohort_positioning(
            client=client,
            rows=[{"date": date(2026, 6, 22), "market": "BTC", "net_taker": 0.3}],
        )
        assert written == 1
        row = client.store["onchain_cohort_positioning"][0]
        json.dumps(row)  # must not raise
        assert row["date"] == "2026-06-22"

    def test_overlay_workspace_skips_shared_register(self, monkeypatch: pytest.MonkeyPatch) -> None:
        overlay = uuid4()
        monkeypatch.setenv("OLYMPUS_OVERLAY_PERSIST", "1")
        overlay_client = FakeSupabaseClient()
        overlay_written = upsert_onchain_cohort_positioning(
            client=overlay_client,
            rows=[{"date": date(2026, 6, 22), "market": "BTC", "net_taker": 0.3}],
            workspace_id=overlay,
        )
        assert overlay_written == 0
        assert overlay_client.store.get("onchain_cohort_positioning", []) == []

        house_client = FakeSupabaseClient()
        house_written = upsert_onchain_cohort_positioning(
            client=house_client,
            rows=[{"date": date(2026, 6, 22), "market": "BTC", "net_taker": 0.3}],
            workspace_id=str(house_workspace_id()),
        )
        omitted = FakeSupabaseClient()
        omitted_written = upsert_onchain_cohort_positioning(
            client=omitted,
            rows=[{"date": date(2026, 6, 22), "market": "BTC", "net_taker": 0.3}],
        )
        assert house_written == 1
        assert omitted_written == 1
        assert house_client.store["onchain_cohort_positioning"][0]["market"] == "BTC"
        assert omitted.store["onchain_cohort_positioning"][0]["market"] == "BTC"


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
        # Thesis / analyst docs are excluded from latest_segments; theses load separately.
        assert ctx.active_theses == []
        assert "thesis/2026-04-19.json" in ctx.latest_segments

    def test_excludes_analyst_and_deliberation_from_latest_segments(self) -> None:
        docs = [
            {
                "date": "2026-04-19",
                "document_key": "analyst/SPY",
                "doc_type": "analyst",
                "payload": {"stance": "hold"},
            },
            {
                "date": "2026-04-19",
                "document_key": "deliberation/SPY",
                "doc_type": "deliberation",
                "payload": {},
            },
            {
                "date": "2026-04-19",
                "document_key": "macro",
                "doc_type": "macro",
                "payload": {"x": 1},
            },
        ]
        client = FakeSupabaseClient(canned_reads={"daily_snapshots": [], "documents": docs})
        ctx = load_prior_context(client=client, run_date=date(2026, 4, 20))
        assert "macro" in ctx.latest_segments
        assert "analyst/SPY" not in ctx.latest_segments
        assert "deliberation/SPY" not in ctx.latest_segments

    def test_overlay_documents_do_not_seed_house_prior_context(self) -> None:
        house = str(house_workspace_id())
        overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        overlay_key = f"overlay/{overlay}/pm-direction-memo"
        docs = [
            {
                "date": "2026-04-19",
                "document_key": overlay_key,
                "doc_type": "pm",
                "payload": {"secret": "overlay"},
                "workspace_id": overlay,
            },
            {
                "date": "2026-04-18",
                "document_key": "macro",
                "doc_type": "macro",
                "payload": {"regime": "house"},
                "workspace_id": house,
            },
            {
                "date": "2026-04-19",
                "document_key": "macro",
                "doc_type": "macro",
                "payload": {"regime": "overlay-copy"},
                "workspace_id": overlay,
            },
        ]
        client = FakeSupabaseClient(canned_reads={"daily_snapshots": [], "documents": docs})
        ctx = load_prior_context(client=client, run_date=date(2026, 4, 20))
        assert overlay_key not in ctx.latest_segments
        assert ctx.latest_segments["macro"]["payload"] == {"regime": "house"}


@pytest.mark.unit
class TestContinuityLoaders:
    def test_load_prior_analyst_summaries_latest_per_ticker(self) -> None:
        docs = [
            {
                "date": "2026-06-17",
                "document_key": "analyst/SHY",
                "payload": {
                    "stance": "hold",
                    "conviction_score": 1,
                    "thesis": "Defensive duration anchor.",
                },
            },
            {
                "date": "2026-06-18",
                "document_key": "analyst/SHY",
                "payload": {
                    "stance": "hold",
                    "conviction_score": 2,
                    "thesis": "Still defensive; yields peaked.",
                },
            },
        ]
        client = FakeSupabaseClient(canned_reads={"documents": docs})
        out = load_prior_analyst_summaries(client, date(2026, 6, 19), ["SHY"])
        assert out["SHY"]["date"] == "2026-06-18"
        assert out["SHY"]["conviction_score"] == 2
        assert "yields peaked" in out["SHY"]["thesis_excerpt"]

    def test_load_prior_analyst_summaries_ignores_overlay_same_key(self) -> None:
        house = str(house_workspace_id())
        overlay = "aaaaaaaa-aaaa-4aaa-8aaa-aaaaaaaaaaaa"
        docs = [
            {
                "date": "2026-06-18",
                "document_key": "analyst/SHY",
                "payload": {"stance": "buy", "conviction_score": 9, "thesis": "overlay"},
                "workspace_id": overlay,
            },
            {
                "date": "2026-06-17",
                "document_key": "analyst/SHY",
                "payload": {
                    "stance": "hold",
                    "conviction_score": 1,
                    "thesis": "house",
                },
                "workspace_id": house,
            },
        ]
        client = FakeSupabaseClient(canned_reads={"documents": docs})
        out = load_prior_analyst_summaries(client, date(2026, 6, 19), ["SHY"])
        assert out["SHY"]["date"] == "2026-06-17"
        assert out["SHY"]["conviction_score"] == 1
        assert out["SHY"]["thesis_excerpt"] == "house"

    def test_load_prior_deliberation_summaries_latest_per_ticker(self) -> None:
        docs = [
            {
                "date": "2026-06-17",
                "document_key": "deliberation/SHY",
                "payload": {
                    "net_stance": "neutral",
                    "conviction_delta": 0,
                    "converged": True,
                    "conclusion": "Hold; duration anchor intact.",
                    "transcript": [{"role": "pm", "text": "x" * 5000}],
                },
            },
            {
                "date": "2026-06-18",
                "document_key": "deliberation/SHY",
                "payload": {
                    "net_stance": "bearish",
                    "conviction_delta": -1,
                    "converged": True,
                    "conclusion": "Trim into strength; yields peaked.",
                    "transcript": [{"role": "pm", "text": "y" * 5000}],
                },
            },
        ]
        client = FakeSupabaseClient(canned_reads={"documents": docs})
        out = load_prior_deliberation_summaries(client, date(2026, 6, 19), ["SHY"])
        assert out["SHY"]["date"] == "2026-06-18"  # latest wins
        assert out["SHY"]["net_stance"] == "bearish"
        assert out["SHY"]["conviction_delta"] == -1
        assert out["SHY"]["converged"] is True
        assert "yields peaked" in out["SHY"]["conclusion_excerpt"]
        # The bulky transcript must NOT survive the slim (carry is excerpt-only).
        assert "transcript" not in out["SHY"]

    def test_load_prior_deliberation_summaries_empty_tickers(self) -> None:
        client = FakeSupabaseClient(canned_reads={"documents": []})
        assert load_prior_deliberation_summaries(client, date(2026, 6, 19), []) == {}

    def test_load_active_theses_rows_excludes_terminal(self) -> None:
        rows = [
            {
                "date": "2026-06-18",
                "thesis_id": "shy-duration",
                "name": "Duration",
                "status": "ACTIVE",
            },
            {
                "date": "2026-06-18",
                "thesis_id": "old-trade",
                "name": "Closed",
                "status": "CLOSED",
            },
            {
                "date": "2026-06-17",
                "thesis_id": "stale",
                "name": "Stale",
                "status": "ACTIVE",
            },
        ]
        client = FakeSupabaseClient(canned_reads={"theses": rows})
        active = load_active_theses_rows(client, date(2026, 6, 19))
        assert [r["thesis_id"] for r in active] == ["shy-duration"]

    def test_load_active_theses_rows_is_not_capped_across_dates(self) -> None:
        """The register must not thin out as history accumulates (#1835).

        The old shape was ``.order("date", desc=True).limit(row_cap)`` followed by a client-side
        filter to the newest date present, so rows from OLDER dates consumed the cap and could
        crowd out the date actually wanted. Here the newest date has 3 theses and the two older
        dates have 40 between them, against ``row_cap=5`` — the old query would have returned
        five rows all from 2026-06-18/17 ordering and yielded an arbitrary slice. The date is now
        resolved first, so the cap applies to one date only.
        """
        newest = [
            {"date": "2026-06-18", "thesis_id": f"live-{i}", "name": f"T{i}", "status": "ACTIVE"}
            for i in range(3)
        ]
        older = [
            {"date": "2026-06-17", "thesis_id": f"old-{i}", "name": f"O{i}", "status": "ACTIVE"}
            for i in range(40)
        ]
        client = FakeSupabaseClient(canned_reads={"theses": newest + older})
        active = load_active_theses_rows(client, date(2026, 6, 19), row_cap=5)
        assert sorted(r["thesis_id"] for r in active) == ["live-0", "live-1", "live-2"]

    def test_load_active_theses_rows_warns_when_it_hits_the_cap(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        """A truncated register admits the duplicate theses it exists to prevent, and the caller
        cannot tell a complete register from a clipped one. So say so out loud."""
        rows = [
            {"date": "2026-06-18", "thesis_id": f"t-{i}", "name": f"T{i}", "status": "ACTIVE"}
            for i in range(6)
        ]
        client = FakeSupabaseClient(canned_reads={"theses": rows})
        with caplog.at_level(logging.WARNING):
            load_active_theses_rows(client, date(2026, 6, 19), row_cap=3)
        assert any("row_cap" in r.message for r in caplog.records)

    def test_load_active_theses_rows_is_quiet_when_well_under_the_cap(
        self, caplog: pytest.LogCaptureFixture
    ) -> None:
        rows = [
            {"date": "2026-06-18", "thesis_id": "t-1", "name": "T1", "status": "ACTIVE"},
        ]
        client = FakeSupabaseClient(canned_reads={"theses": rows})
        with caplog.at_level(logging.WARNING):
            load_active_theses_rows(client, date(2026, 6, 19), row_cap=100)
        assert not [r for r in caplog.records if "row_cap" in r.message]

    def test_load_portfolio_performance_snapshot(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "nav_history": [
                    {"date": "2026-06-18", "nav": 102.5, "cash_pct": 30, "invested_pct": 70}
                ],
                "portfolio_metrics": [
                    {
                        "date": "2026-06-18",
                        "pnl_pct": 2.5,
                        "sharpe": 1.1,
                        "volatility": 8.0,
                        "max_drawdown": -3.0,
                        "alpha": 0.4,
                    }
                ],
            }
        )
        snap = load_portfolio_performance_snapshot(client, date(2026, 6, 19))
        assert snap["nav_date"] == "2026-06-18"
        assert snap["nav"] == 102.5
        assert snap["metrics"]["sharpe"] == 1.1


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
class TestQueryPriceDeltasRowCap:
    """Regression (#2484): triage price deltas must not drop tickers under the row cap.

    ``query_price_deltas`` fetches up to ``lookback_days`` calendar rows per ticker.
    Supabase truncates an unbounded PostgREST response at 1000 rows; a truncated
    ticker is silently dropped and the rule engine treats a missing key as no signal.
    """

    CAP = 1000
    LOOKBACK = _DEFAULT_PRICE_LOOKBACK_DAYS

    def _capped_client(self, tickers: list[str]) -> FakeSupabaseClient:
        run_date = date(2026, 4, 27)
        rows = [
            {
                "date": (run_date - timedelta(days=offset)).isoformat(),
                "ticker": ticker,
                "close": 100.0 + index + (0.5 if offset == 1 else 0.0),
            }
            for index, ticker in enumerate(tickers)
            for offset in range(1, self.LOOKBACK + 2)
        ]
        cap = self.CAP

        class _Capped(FakeSupabaseClient):
            def table(self, name: str):  # type: ignore[no-untyped-def]
                query = super().table(name)
                if name != "price_history":
                    return query
                inner = query.execute

                def _execute():  # type: ignore[no-untyped-def]
                    resp = inner()
                    resp.data = list(resp.data or [])[:cap]
                    return resp

                query.execute = _execute  # type: ignore[method-assign]
                return query

        return _Capped(canned_reads={"price_history": rows})

    def test_wide_universe_is_fully_priced_under_the_row_cap(self) -> None:
        tickers = [f"TK{index:03d}" for index in range(80)]
        assert len(tickers) * (self.LOOKBACK + 1) > self.CAP, "universe must exceed the cap"
        client = self._capped_client(tickers)
        out = query_price_deltas(
            client=client,
            tickers=tuple(tickers),
            run_date=date(2026, 4, 27),
            lookback_days=self.LOOKBACK,
        )
        missing = sorted(set(tickers) - set(out))
        assert not missing, (
            f"{len(missing)} ticker(s) lost to the row cap ({missing[:5]}...) — "
            "a truncated read is reported as no signal"
        )

    def test_batch_is_derived_from_the_lookback(self) -> None:
        batch = _price_delta_ticker_batch(self.LOOKBACK)
        worst_case = batch * (self.LOOKBACK + 1)
        assert worst_case <= self.CAP, (
            f"a full batch can return {worst_case} rows, over the {self.CAP} cap"
        )


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


@pytest.mark.unit
class TestLoadPriorBook:
    def test_returns_latest_date_strictly_before_run_date(self) -> None:
        client = FakeSupabaseClient(
            canned_reads={
                "positions": [
                    {"date": "2026-06-17", "ticker": "SPY", "weight_pct": 20},
                    {"date": "2026-06-17", "ticker": "CASH", "weight_pct": 80},
                    {"date": "2026-06-15", "ticker": "BIL", "weight_pct": 100},
                ]
            }
        )
        book = load_prior_book(client, date(2026, 6, 18))
        assert {r["ticker"] for r in book} == {"SPY", "CASH"}
        assert all(r["date"] == "2026-06-17" for r in book)

    def test_first_run_returns_empty(self) -> None:
        client = FakeSupabaseClient(canned_reads={"positions": []})
        assert load_prior_book(client, date(2026, 6, 17)) == []

    def test_prior_book_current_weights_maps_tickers(self) -> None:
        weights = prior_book_current_weights(
            [
                {"ticker": "SPY", "weight_pct": 20},
                {"ticker": "CASH", "weight_pct": 80},
            ]
        )
        assert weights == {"SPY": 20.0, "CASH": 80.0}
