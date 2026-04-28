"""Phase 9 closed-loop reflection — Phase A persist + Phase B resolve (#432).

Covers:
- Phase A writes one ``decision_log`` row per watchlist ticker per run.
- Pending row payload shape (columns + thesis truncation).
- Phase B skips rows still inside the holding window.
- Alpha calculation (ticker_return - benchmark_return).
- Reflector LLM is called once per due decision (not per skipped row).
- Resolved rows have status / alpha / lesson / resolved_at populated.
- ``PriorContext.decision_lessons`` populated with last N (5 same-ticker + 3 cross-ticker).
- Missing returns data → graceful skip (row stays pending).
- Idempotency — re-resolving a resolved row preserves the original reflection.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa: scored-lint suppression — heterogeneous fake-row dict shape
from uuid import UUID

import pytest

from digiquant.atlas.decision_log import (
    DEFAULT_BENCHMARK,
    DEFAULT_HOLDING_DAYS,
    THESIS_MAX_CHARS,
    ReflectorOutput,
    fetch_recent_lessons,
    persist_pending,
    resolve_pending,
)
from digiquant.hermes.phases.phase9_evolution import Phase9Deps, build_phase9
from digiquant.atlas.phases.preflight import (
    PreflightDeps,
    PreflightReflectDeps,
    build_preflight_node,
    build_preflight_reflect_node,
)
from digiquant.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


# ─── Fixtures ──────────────────────────────────────────────────────────────


_RUN_ID = UUID("11111111-2222-3333-4444-555555555555")


def _seed_state_with_analysts(
    *,
    watchlist: tuple[str, ...] = ("AAPL", "MSFT"),
    preferences: dict[str, Any] | None = None,
    run_date: date = date(2026, 4, 26),
) -> AtlasResearchState:
    """Build an AtlasResearchState with Phase 7C analyst rows already populated."""
    state = AtlasResearchState(
        run_id=_RUN_ID,
        run_type="baseline",
        run_date=run_date,
        config=AtlasConfigBundle(
            watchlist=list(watchlist),
            preferences=preferences or {},
        ),
    )
    state.phase7c_analysts = {
        ticker: {
            "ticker": ticker,
            "conviction_score": 3,
            "stance": "buy",
            "thesis": f"Thesis for {ticker}",
            "risks": "",
            "sources": [],
        }
        for ticker in watchlist
    }
    return state


def _stub_reflector(prompt_inputs: dict[str, Any]) -> ReflectorOutput:
    """Deterministic reflector for tests — echoes the alpha into the lesson."""
    alpha = prompt_inputs.get("alpha", 0.0)
    return ReflectorOutput(
        reflection=(
            f"Reflection for {prompt_inputs.get('ticker')}: alpha={alpha:.4f}. "
            "Thesis was directionally informative but underweighted realized factor."
        )
    )


def _price_history_rows(
    *,
    ticker: str,
    start_date: date,
    closes: list[float],
) -> list[dict[str, Any]]:
    """Build a list of consecutive-day price_history rows.

    Trading-day-aware: skips weekends so the test data matches what real
    ETL would produce. Mirrors :func:`query_returns_window`'s assumption
    that ``price_history`` only contains rows for actual trading days.
    """
    from datetime import timedelta

    rows: list[dict[str, Any]] = []
    d = start_date
    for c in closes:
        # Skip weekends.
        while d.weekday() >= 5:
            d = d + timedelta(days=1)
        rows.append({"date": d.isoformat(), "ticker": ticker, "close": c})
        d = d + timedelta(days=1)
    return rows


# ─── Phase A: persist_pending ──────────────────────────────────────────────


@pytest.mark.unit
class TestPhaseAWritesPending:
    def test_phase9_writes_pending_rows_per_ticker(self) -> None:
        """One row per ticker in Phase 7C analyst output."""
        client = FakeSupabaseClient()
        state = _seed_state_with_analysts(watchlist=("AAPL", "MSFT", "GOOG"))

        rows_written = persist_pending(client=client, state=state)

        assert rows_written == 3
        assert "decision_log" in client.store
        tickers = sorted(r["ticker"] for r in client.store["decision_log"])
        assert tickers == ["AAPL", "GOOG", "MSFT"]

    def test_pending_row_payload_shape(self) -> None:
        """Verify columns + truncation of thesis to 800 chars."""
        client = FakeSupabaseClient()
        state = _seed_state_with_analysts(watchlist=("AAPL",))
        # Inject a long thesis to exercise truncation.
        long_thesis = "A" * 900 + "B" * 100  # 1000 chars total
        state.phase7c_analysts["AAPL"]["thesis"] = long_thesis

        persist_pending(client=client, state=state)

        row = client.store["decision_log"][0]
        # Columns from migration 026.
        assert set(row.keys()) >= {
            "run_id",
            "run_date",
            "ticker",
            "stance",
            "conviction",
            "thesis",
            "benchmark",
            "holding_days",
            "status",
        }
        assert row["run_id"] == str(_RUN_ID)
        assert row["run_date"] == "2026-04-26"
        assert row["ticker"] == "AAPL"
        assert row["stance"] == "buy"
        assert row["conviction"] == 3
        assert row["benchmark"] == DEFAULT_BENCHMARK
        assert row["holding_days"] == DEFAULT_HOLDING_DAYS
        assert row["status"] == "pending"
        # Truncation: 800 chars max.
        assert len(row["thesis"]) == THESIS_MAX_CHARS
        assert row["thesis"] == "A" * 800
        # Idempotency on (run_id, ticker).
        assert row["_on_conflict"] == "run_id,ticker"

    def test_phase9_node_calls_persist_pending_when_deps_wired(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Integration: the Phase 9 node calls persist_pending when Phase9Deps is provided."""
        from digiquant.hermes.phases import phase9_evolution

        client = FakeSupabaseClient()
        state = _seed_state_with_analysts(watchlist=("AAPL",))
        state.phase7_digest = {"bias": "neutral"}

        called: dict[str, int] = {"persist": 0}

        def stub_persist(*, client: Any, state: Any) -> int:  # noqa: ARG001
            called["persist"] += 1
            return 1

        monkeypatch.setattr(phase9_evolution, "persist_pending", stub_persist)
        # Also stub the LLM call so this test stays hermetic.
        monkeypatch.setattr(
            "digigraph.graph.research_agent.chat_completion",
            lambda *a, **kw: (
                '{"sources":{"scored":[],"discoveries":[]},'
                '"quality":{"predictions_checked":[],'
                '"rubric":{"accuracy":4,"completeness":4,"actionability":3,'
                '"conciseness":4,"source_quality":5}},'
                '"proposals":{"proposals":[]}}'
            ),
        )

        phase = build_phase9(deps=Phase9Deps(client=client))
        node = phase.nodes[0].run
        node(state)

        assert called["persist"] == 1

    def test_phase9_node_skips_persist_when_deps_none(
        self, monkeypatch: pytest.MonkeyPatch
    ) -> None:
        """Default behaviour preserved: deps=None means no Supabase write."""
        from digiquant.hermes.phases import phase9_evolution

        called: dict[str, int] = {"persist": 0}

        def stub_persist(*, client: Any, state: Any) -> int:  # noqa: ARG001
            called["persist"] += 1
            return 1

        monkeypatch.setattr(phase9_evolution, "persist_pending", stub_persist)
        monkeypatch.setattr(
            "digigraph.graph.research_agent.chat_completion",
            lambda *a, **kw: (
                '{"sources":{"scored":[],"discoveries":[]},'
                '"quality":{"predictions_checked":[],'
                '"rubric":{"accuracy":4,"completeness":4,"actionability":3,'
                '"conciseness":4,"source_quality":5}},'
                '"proposals":{"proposals":[]}}'
            ),
        )

        state = _seed_state_with_analysts(watchlist=("AAPL",))
        state.phase7_digest = {"bias": "neutral"}

        phase = build_phase9(deps=None)
        node = phase.nodes[0].run
        node(state)

        assert called["persist"] == 0

    def test_persist_skips_payload_missing_stance(self) -> None:
        """Defensive: corrupt analyst payload is dropped, not persisted half-formed."""
        client = FakeSupabaseClient()
        state = _seed_state_with_analysts(watchlist=("AAPL", "MSFT"))
        # Corrupt one entry by removing required field.
        del state.phase7c_analysts["MSFT"]["stance"]

        rows_written = persist_pending(client=client, state=state)

        assert rows_written == 1
        assert client.store["decision_log"][0]["ticker"] == "AAPL"

    def test_persist_uses_holding_days_preference(self) -> None:
        """preferences[holding_days] overrides the default."""
        client = FakeSupabaseClient()
        state = _seed_state_with_analysts(
            watchlist=("AAPL",),
            preferences={"holding_days": 10},
        )
        persist_pending(client=client, state=state)
        assert client.store["decision_log"][0]["holding_days"] == 10


# ─── Phase B: resolve_pending ──────────────────────────────────────────────


@pytest.mark.unit
class TestPhaseBResolvesPending:
    def test_resolve_skips_rows_inside_holding_window(self) -> None:
        """run_date + holding_days <= today is required."""
        # Decision was made 3 days ago with a 5-day holding window — not yet due.
        run_date = date(2026, 4, 26)
        # Pending row dated 2026-04-23 with holding_days=5 → due on 2026-04-28.
        pending_row = {
            "id": "row-1",
            "run_id": str(_RUN_ID),
            "run_date": "2026-04-23",  # within 5 days of run_date
            "ticker": "AAPL",
            "stance": "buy",
            "conviction": 3,
            "thesis": "t",
            "benchmark": "SPY",
            "holding_days": 5,
            "status": "pending",
        }
        client = FakeSupabaseClient(canned_reads={"decision_log": [pending_row]})

        called: list[Any] = []

        def reflector(_inputs: dict[str, Any]) -> ReflectorOutput:
            called.append(_inputs)
            return ReflectorOutput(reflection="x")

        resolved = resolve_pending(
            client=client,
            run_date=run_date,
            reflector=reflector,
        )

        assert resolved == 0
        # Reflector NOT called because the row was filtered out by the
        # server-side ``run_date < floor`` query.
        assert called == []

    def test_resolve_computes_alpha_correctly(self) -> None:
        """Synthetic returns: ticker +3%, SPY +1% → alpha = 2%."""
        decision_run_date = date(2026, 4, 13)  # Mon — 13+ days before the run_date below
        run_date = date(2026, 4, 27)

        pending_row = {
            "id": "row-AAPL",
            "run_id": str(_RUN_ID),
            "run_date": decision_run_date.isoformat(),
            "ticker": "AAPL",
            "stance": "buy",
            "conviction": 3,
            "thesis": "t",
            "benchmark": "SPY",
            "holding_days": 5,
            "status": "pending",
        }
        # Build 6 trading days for AAPL: 100 → 103 (+3% over 5 trading days).
        aapl_rows = _price_history_rows(
            ticker="AAPL",
            start_date=decision_run_date,
            closes=[100.0, 100.5, 101.0, 101.5, 102.0, 103.0],
        )
        spy_rows = _price_history_rows(
            ticker="SPY",
            start_date=decision_run_date,
            closes=[400.0, 400.5, 401.0, 402.0, 403.0, 404.0],
        )
        # SPY return: (404 - 400) / 400 = 0.01 (1%); alpha = 0.03 - 0.01 = 0.02.
        client = FakeSupabaseClient(
            canned_reads={
                "decision_log": [pending_row],
                "price_history": aapl_rows + spy_rows,
            }
        )
        # Need to pre-populate the store so update() can find the row.
        client.store["decision_log"] = [dict(pending_row)]

        captured: list[dict[str, Any]] = []

        def reflector(inputs: dict[str, Any]) -> ReflectorOutput:
            captured.append(inputs)
            return ReflectorOutput(reflection=f"alpha={inputs['alpha']:.4f}")

        resolved = resolve_pending(
            client=client,
            run_date=run_date,
            reflector=reflector,
        )
        assert resolved == 1
        assert len(captured) == 1
        prompt = captured[0]
        assert prompt["ticker"] == "AAPL"
        assert prompt["actual_return"] == pytest.approx(0.03)
        assert prompt["benchmark_return"] == pytest.approx(0.01)
        assert prompt["alpha"] == pytest.approx(0.02)

    def test_resolve_calls_reflector_once_per_due_decision(self) -> None:
        """Two due rows → exactly two LLM calls."""
        decision_run_date = date(2026, 4, 13)
        run_date = date(2026, 4, 27)

        pending_rows = [
            {
                "id": f"row-{ticker}",
                "run_id": str(_RUN_ID),
                "run_date": decision_run_date.isoformat(),
                "ticker": ticker,
                "stance": "buy",
                "conviction": 3,
                "thesis": "t",
                "benchmark": "SPY",
                "holding_days": 5,
                "status": "pending",
            }
            for ticker in ("AAPL", "MSFT")
        ]
        # Each ticker needs 6 days of price history.
        price_rows: list[dict[str, Any]] = []
        for ticker in ("AAPL", "MSFT", "SPY"):
            price_rows.extend(
                _price_history_rows(
                    ticker=ticker,
                    start_date=decision_run_date,
                    closes=[100.0, 100.5, 101.0, 101.5, 102.0, 103.0],
                )
            )
        client = FakeSupabaseClient(
            canned_reads={"decision_log": pending_rows, "price_history": price_rows}
        )
        client.store["decision_log"] = [dict(r) for r in pending_rows]

        call_count = {"n": 0}

        def reflector(_inputs: dict[str, Any]) -> ReflectorOutput:
            call_count["n"] += 1
            return ReflectorOutput(reflection="x")

        resolved = resolve_pending(client=client, run_date=run_date, reflector=reflector)
        assert resolved == 2
        assert call_count["n"] == 2

    def test_resolve_updates_row_status_and_fields(self) -> None:
        """status='resolved' + alpha + reflection + resolved_at populated."""
        decision_run_date = date(2026, 4, 13)
        run_date = date(2026, 4, 27)
        pending_row = {
            "id": "row-AAPL",
            "run_id": str(_RUN_ID),
            "run_date": decision_run_date.isoformat(),
            "ticker": "AAPL",
            "stance": "buy",
            "conviction": 3,
            "thesis": "t",
            "benchmark": "SPY",
            "holding_days": 5,
            "status": "pending",
        }
        # Both AAPL and SPY return +2%.
        price_rows = _price_history_rows(
            ticker="AAPL",
            start_date=decision_run_date,
            closes=[100.0, 100.5, 101.0, 101.2, 101.5, 102.0],
        ) + _price_history_rows(
            ticker="SPY",
            start_date=decision_run_date,
            closes=[400.0, 400.5, 401.0, 401.2, 401.5, 408.0],
        )
        client = FakeSupabaseClient(
            canned_reads={"decision_log": [pending_row], "price_history": price_rows}
        )
        client.store["decision_log"] = [dict(pending_row)]

        resolve_pending(client=client, run_date=run_date, reflector=_stub_reflector)

        # Inspect the in-memory store to confirm the update was applied.
        row = client.store["decision_log"][0]
        assert row["status"] == "resolved"
        assert row["actual_return"] is not None
        assert row["alpha"] is not None
        assert isinstance(row["reflection"], str)
        assert "alpha=" in row["reflection"]
        assert row["resolved_at"] is not None

    def test_resolve_idempotent_on_already_resolved_rows(self) -> None:
        """Re-running Phase 9 must not overwrite an existing reflection (AC #8)."""
        decision_run_date = date(2026, 4, 13)
        run_date = date(2026, 4, 27)
        # Pre-resolved row: status='resolved' with a saved reflection.
        already_resolved = {
            "id": "row-OLD",
            "run_id": str(_RUN_ID),
            "run_date": decision_run_date.isoformat(),
            "ticker": "AAPL",
            "stance": "buy",
            "conviction": 3,
            "thesis": "t",
            "benchmark": "SPY",
            "holding_days": 5,
            "status": "resolved",
            "actual_return": 0.05,
            "alpha": 0.02,
            "reflection": "ORIGINAL — must not be clobbered.",
            "resolved_at": "2026-04-20T00:00:00+00:00",
        }
        # Phase B's `query_pending_decisions` filters on status='pending',
        # so the already-resolved row should NOT be returned at all.
        client = FakeSupabaseClient(canned_reads={"decision_log": [already_resolved]})
        client.store["decision_log"] = [dict(already_resolved)]

        called: list[Any] = []

        def reflector(_inputs: dict[str, Any]) -> ReflectorOutput:
            called.append(_inputs)
            return ReflectorOutput(reflection="NEW LESSON")

        resolved = resolve_pending(client=client, run_date=run_date, reflector=reflector)
        assert resolved == 0
        assert called == []
        # Original reflection unchanged.
        assert client.store["decision_log"][0]["reflection"] == "ORIGINAL — must not be clobbered."

    def test_missing_returns_data_skips_resolution(self) -> None:
        """Graceful handling when ticker has no price_history row (AC #7)."""
        decision_run_date = date(2026, 4, 13)
        run_date = date(2026, 4, 27)
        pending_row = {
            "id": "row-NEW",
            "run_id": str(_RUN_ID),
            "run_date": decision_run_date.isoformat(),
            "ticker": "ZZZ",  # No price data for this ticker.
            "stance": "buy",
            "conviction": 3,
            "thesis": "t",
            "benchmark": "SPY",
            "holding_days": 5,
            "status": "pending",
        }
        # Provide SPY rows but NO ZZZ rows — query_returns_window returns None.
        spy_rows = _price_history_rows(
            ticker="SPY",
            start_date=decision_run_date,
            closes=[400.0, 401.0, 402.0, 403.0, 404.0, 405.0],
        )
        client = FakeSupabaseClient(
            canned_reads={"decision_log": [pending_row], "price_history": spy_rows}
        )
        client.store["decision_log"] = [dict(pending_row)]

        called: list[Any] = []

        def reflector(_inputs: dict[str, Any]) -> ReflectorOutput:
            called.append(_inputs)
            return ReflectorOutput(reflection="x")

        resolved = resolve_pending(client=client, run_date=run_date, reflector=reflector)
        assert resolved == 0
        assert called == []
        # Row remains pending — next run will retry.
        assert client.store["decision_log"][0]["status"] == "pending"


# ─── PriorContext injection ────────────────────────────────────────────────


@pytest.mark.unit
class TestLessonsInjection:
    def test_lessons_injected_into_prior_context(self) -> None:
        """PriorContext.decision_lessons populated; same/cross limits respected."""
        run_date = date(2026, 4, 27)

        # Build 10 same-ticker resolved rows for AAPL + 5 cross-ticker resolved rows.
        # The query should return the latest 5 same-ticker + latest 3 cross-ticker = 8 total.
        same_ticker_rows = [
            {
                "id": f"aapl-{i}",
                "run_id": str(_RUN_ID),
                "run_date": f"2026-04-{10 + i:02d}",
                "ticker": "AAPL",
                "stance": "buy",
                "conviction": 3,
                "thesis": f"thesis aapl {i}",
                "benchmark": "SPY",
                "holding_days": 5,
                "status": "resolved",
                "actual_return": 0.01 * i,
                "alpha": 0.005 * i,
                "reflection": f"lesson {i}",
                "resolved_at": "2026-04-26T00:00:00+00:00",
            }
            for i in range(10)
        ]
        cross_ticker_rows = [
            {
                "id": f"msft-{i}",
                "run_id": str(_RUN_ID),
                "run_date": f"2026-04-{15 + i:02d}",
                "ticker": "MSFT",
                "stance": "hold",
                "conviction": 1,
                "thesis": f"thesis msft {i}",
                "benchmark": "SPY",
                "holding_days": 5,
                "status": "resolved",
                "actual_return": 0.02 * i,
                "alpha": 0.01 * i,
                "reflection": f"msft lesson {i}",
                "resolved_at": "2026-04-26T00:00:00+00:00",
            }
            for i in range(5)
        ]
        client = FakeSupabaseClient(
            canned_reads={"decision_log": same_ticker_rows + cross_ticker_rows}
        )

        lessons = fetch_recent_lessons(
            client=client,
            run_date=run_date,
            watchlist=("AAPL",),
            same_ticker_limit=5,
            cross_ticker_limit=3,
        )

        # 5 AAPL + 3 MSFT = 8.
        assert len(lessons) == 8
        aapl_lessons = [row for row in lessons if row["ticker"] == "AAPL"]
        msft_lessons = [row for row in lessons if row["ticker"] == "MSFT"]
        assert len(aapl_lessons) == 5
        assert len(msft_lessons) == 3
        # Same-ticker lessons should be the latest 5 (highest run_date).
        aapl_dates = sorted(row["run_date"] for row in aapl_lessons)
        assert aapl_dates == ["2026-04-15", "2026-04-16", "2026-04-17", "2026-04-18", "2026-04-19"]

    def test_preflight_loads_decision_lessons_into_prior_context(self) -> None:
        """Preflight calls fetch_recent_lessons and stores the result."""
        run_date = date(2026, 4, 26)
        resolved_row = {
            "id": "row-OLD",
            "run_id": str(_RUN_ID),
            "run_date": "2026-04-15",
            "ticker": "AAPL",
            "stance": "buy",
            "conviction": 3,
            "thesis": "t",
            "benchmark": "SPY",
            "holding_days": 5,
            "status": "resolved",
            "actual_return": 0.05,
            "alpha": 0.02,
            "reflection": "Past lesson on AAPL.",
            "resolved_at": "2026-04-22T00:00:00+00:00",
        }
        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [],
                "macro_series_observations": [],
                "decision_log": [resolved_row],
            }
        )
        deps = PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(watchlist=["AAPL"]),
        )
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=run_date)

        out = node(state)

        assert "prior_context" in out
        ctx = out["prior_context"]
        assert len(ctx.decision_lessons) == 1
        assert ctx.decision_lessons[0]["ticker"] == "AAPL"
        assert ctx.decision_lessons[0]["reflection"] == "Past lesson on AAPL."

    def test_pm_phase_inputs_include_past_context(self) -> None:
        """Phase 7D's _pm_node passes prior_context.decision_lessons as past_context."""
        from unittest.mock import patch

        from digiquant.hermes.phases.phase7d_pm import _pm_node
        from digiquant.atlas.state import PriorContext

        lessons = [{"ticker": "AAPL", "reflection": "Past lesson", "alpha": 0.02}]
        state = AtlasResearchState(
            run_type="baseline",
            run_date=date(2026, 4, 26),
            config=AtlasConfigBundle(watchlist=["AAPL"]),
            prior_context=PriorContext(decision_lessons=lessons),
        )
        state.phase7c_analysts = {
            "AAPL": {"ticker": "AAPL", "stance": "buy", "conviction_score": 3, "thesis": "x"}
        }

        captured: dict[str, Any] = {}

        def fake_run(skill_text, phase_inputs, **kw):  # noqa: ARG001
            captured.update(phase_inputs)
            from digiquant.hermes.phases.phase7d_pm import RebalanceDecision

            return RebalanceDecision()

        with patch("digigraph.graph.research_agent.run_research_agent", side_effect=fake_run):
            _pm_node(state)

        assert "past_context" in captured
        assert captured["past_context"] == lessons


# ─── Preflight reflect node integration ────────────────────────────────────


@pytest.mark.unit
class TestPreflightReflectNode:
    def test_reflect_node_invokes_resolve_pending(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """The reflect node calls resolve_pending and returns an empty update."""
        from digiquant.atlas.phases import preflight as preflight_module

        called: dict[str, int] = {"resolve": 0}

        def stub_resolve(*, client: Any, run_date: Any, reflector: Any) -> int:  # noqa: ARG001
            called["resolve"] += 1
            return 0

        monkeypatch.setattr(preflight_module, "resolve_pending", stub_resolve)

        client = FakeSupabaseClient()
        deps = PreflightReflectDeps(client=client, reflector=_stub_reflector)
        node = build_preflight_reflect_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))

        out = node(state)

        assert called["resolve"] == 1
        # Empty update — side effect is the Supabase write.
        assert out == {}


# ─── Graph-deps wiring ─────────────────────────────────────────────────────


@pytest.mark.unit
class TestGraphDepsWiring:
    def test_phase9_deps_threaded_through_build_atlas_graph(self) -> None:
        """build_atlas_graph compiles cleanly when Phase9Deps is wired."""
        from digiquant.atlas.graph import AtlasGraphDeps, build_atlas_graph

        client = FakeSupabaseClient()
        deps = AtlasGraphDeps(
            preflight=PreflightDeps(client=client, config_loader=lambda: AtlasConfigBundle()),
            phase9=Phase9Deps(client=client),
            preflight_reflect=PreflightReflectDeps(client=client, reflector=_stub_reflector),
        )
        graph = build_atlas_graph("baseline", deps=deps, watchlist=("AAPL",))
        assert graph is not None
