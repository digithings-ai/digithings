"""Atlas → Hermes chain integration test.

Exercises :func:`digiquant.olympus.hermes.chain.run_atlas_then_hermes` end-to-end
through the same simulator harness the per-phase tests use. Validates the
chain's three responsibilities:

1. Atlas runs research-only (publish=None during the Atlas pass).
2. Hermes consumes the populated state and runs analyst → debate → PM →
   reflection.
3. ``publish_phase`` flushes the fully populated state once at the end.

Two scenarios:

- ``test_baseline_chain_populates_both_engines`` — full baseline run hits
  every phase. State should carry research outputs (phase1..7) AND analysis
  outputs (phase_hermes.asset_analysts, pm_direction_memo, sized_book) by the
  end. The fake Supabase client should record exactly one daily_snapshots
  upsert and the analyst/PM document writes.
- ``test_monthly_chain_short_circuits_at_atlas`` — monthly run uses
  Atlas's phase_monthly path; Hermes does not run; state's H-slots stay
  unset.
"""

from __future__ import annotations

from datetime import date
from typing import Any  # noqa  # scored-lint suppression: test fixture dicts
from unittest.mock import patch

import pytest

from digiquant.olympus.atlas.graph import AtlasInput

from digiquant.olympus.atlas.testing.simulator import simulated_pipeline


@pytest.mark.unit
class TestChainBaseline:
    def test_baseline_chain_populates_both_engines(self) -> None:
        """Atlas → Hermes chain: research + analysis slots both populated."""
        with simulated_pipeline(watchlist=("AAPL",), phase9=True) as run:
            final = run.invoke(
                AtlasInput(
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )

        # Research outputs (Atlas).
        assert final.phase7_digest is not None
        assert "master-digest" in (final.phase7_digest.get("segment") or "")

        # Analysis outputs (Hermes H5–H8).
        assert "AAPL" in final.phase_hermes.asset_analysts, (
            "Hermes H5 should have populated phase_hermes.asset_analysts"
        )
        assert final.phase_hermes.pm_direction_memo is not None, (
            "Hermes H7 should have populated pm_direction_memo"
        )
        assert final.phase_hermes.sized_book is not None, (
            "Hermes H8 should have populated sized_book"
        )

    def test_baseline_chain_publish_writes_after_hermes(self) -> None:
        """Terminal publish runs once with both engines' outputs in scope."""
        with simulated_pipeline(watchlist=("AAPL",), phase9=True) as run:
            final = run.invoke(
                AtlasInput(
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )

        # publish_phase records every publish via the FakeSupabaseClient.
        store = run.client.store
        # daily_snapshots upserted exactly once for the baseline digest.
        assert "daily_snapshots" in store
        snapshots = store["daily_snapshots"]
        assert len(snapshots) == 1, (
            f"expected exactly one daily_snapshots write, got {len(snapshots)}"
        )

        # documents include the per-segment writes + the digest doc + the
        # analyst payloads. The chain ordering means phase7c_analysts['AAPL']
        # exists in state before publish runs, so the analyst doc is in the store.
        documents = store.get("documents", [])
        document_keys = {row.get("document_key") for row in documents}
        # Atlas's research segments published — alt-* and asset-class
        # docs land here. (The synthesis digest goes to daily_snapshots,
        # not documents/.)
        assert "alt-sentiment-news" in document_keys
        assert "bonds" in document_keys
        # Hermes's analyst payload published in the same pass.
        assert "analyst/AAPL" in document_keys, (
            f"analyst document missing from publish; saw keys: {sorted(k for k in document_keys if k)}"
        )
        # Final state from the chain still has the analyst payload populated.
        assert "AAPL" in final.phase_hermes.asset_analysts


@pytest.mark.unit
class TestChainMaterialization:
    def test_pm_decision_materializes_positions_and_nav(self) -> None:
        """H8 sized book materializes to positions + base-100 NAV (#700)."""
        with simulated_pipeline(
            watchlist=("AAPL",),
            preferences={
                "max_single_etf_pct": 100,
                "max_sector_pct": 100,
                "target_portfolio_vol": 1.0e6,
                "weight_increment_pct": 0,
                "min_conviction": 2.0,
            },
            overrides={
                "PMDirectionMemo": {
                    "schema_version": "1.0",
                    "date": "2026-04-26",
                    "roster": [
                        {
                            "ticker": "AAPL",
                            "direction": "long",
                            "conviction_rank": 1,
                            "narrative": "",
                        }
                    ],
                    "memo": "synthetic",
                },
                "AnalystPayload": {
                    "ticker": "AAPL",
                    "conviction_score": 5,
                    "stance": "buy",
                    "thesis": "x",
                    "risks": "x",
                    "sources": [],
                },
            },
        ) as run:
            final = run.invoke(AtlasInput(run_date=date(2026, 4, 26), watchlist=("AAPL",)))

        assert final.phase_hermes.sized_book is not None
        store = run.client.store
        positions = {r["ticker"]: r for r in store.get("positions", [])}
        assert positions["AAPL"]["weight_pct"] == 100.0
        navs = store.get("nav_history", [])
        assert len(navs) == 1
        assert navs[0]["nav"] == 100.0  # first-ever run seeds the index at 100

    def test_commit_run_off_writes_no_book(self) -> None:
        with simulated_pipeline(
            watchlist=("AAPL",),
            commit_run=False,
            overrides={
                "PMDirectionMemo": {
                    "schema_version": "1.0",
                    "date": "2026-04-26",
                    "roster": [
                        {
                            "ticker": "AAPL",
                            "direction": "long",
                            "conviction_rank": 1,
                            "narrative": "",
                        }
                    ],
                    "memo": "x",
                }
            },
        ) as run:
            run.invoke(AtlasInput(run_date=date(2026, 4, 26), watchlist=("AAPL",)))
        assert "positions" not in run.client.store
        assert "nav_history" not in run.client.store


@pytest.mark.unit
class TestChainDailyCadence:
    def test_daily_chain_populates_both_engines(self) -> None:
        """Atlas → Hermes chain with daily cadence: research + analysis slots populated."""
        with simulated_pipeline(watchlist=("AAPL",), phase9=True) as run:
            final = run.invoke(
                AtlasInput(
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )

        assert final.phase7_digest is not None
        assert "master-digest" in (final.phase7_digest.get("segment") or "")
        assert "AAPL" in final.phase_hermes.asset_analysts
        assert final.phase_hermes.pm_direction_memo is not None
        assert final.phase_hermes.sized_book is not None


@pytest.mark.unit
class TestChainResearchGate:
    """#944: Hermes must not run/commit when the Atlas pass produced no fresh research.

    The Jun-20 incident: Atlas crashed on empty LLM responses (``openrouter/auto``), yet the
    chain swallowed the crash (``_safe_invoke_graph``) and Hermes ran, booking a pm-rebalance
    on 2-day-stale prior context. The gate must skip the Hermes commit entirely on an
    insufficient Atlas pass and record the skip so the run is gated (CI retries).
    """

    def test_failed_atlas_skips_hermes(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digiquant.olympus.atlas.state import PhaseError
        from digiquant.olympus.hermes import chain as chain_mod

        hermes_built: list[bool] = []

        def _fake_safe_invoke(graph: Any, state: Any, *_a: Any, **_k: Any) -> Any:
            # Simulate the Atlas pass crashing at the chain level: _safe_invoke_graph records
            # a chain/atlas error and returns the last-good (research-empty) state.
            label = _a[-1] if _a else _k.get("label")
            if label == "atlas":
                state.errors.append(
                    PhaseError(
                        phase="chain",
                        node="atlas",
                        message="empty LLM response from 'openrouter/auto'",
                        retryable=True,
                    )
                )
            return state

        def _fake_build_hermes_graph(**_kwargs: Any) -> Any:
            hermes_built.append(True)

            class _Graph:
                def invoke(self, state: Any, *_a: Any, **_k: Any) -> Any:
                    return state

            return _Graph()

        monkeypatch.setattr(chain_mod, "_safe_invoke_graph", _fake_safe_invoke)
        monkeypatch.setattr(chain_mod, "build_atlas_graph", lambda *_a, **_k: object())
        monkeypatch.setattr(chain_mod, "_run_terminal_phase", lambda *_a, **_k: _a[2])
        monkeypatch.setattr(chain_mod, "build_hermes_graph", _fake_build_hermes_graph)

        with simulated_pipeline(watchlist=("AAPL",)) as run:
            final = chain_mod.run_atlas_then_hermes(
                atlas_input=AtlasInput(run_date=date(2026, 6, 20), watchlist=("AAPL",)),
                deps=chain_mod.ChainDeps(atlas=run.deps, hermes=run.hermes_deps),
            )

        assert hermes_built == [], "Hermes must be skipped when Atlas produced no research"
        assert any(getattr(e, "node", "") == "hermes-skipped" for e in final.errors), (
            "the skip must be recorded as a chain error so the run is gated for retry"
        )


@pytest.mark.unit
class TestChainHeldInvariant:
    """``run_atlas_then_hermes`` threads prior-book holdings into the 7C/7CD cap (#936).

    The Jun-18 regression: a held name (IJR) fell outside the
    ``ATLAS_MAX_ANALYSTS`` window and was dropped from the fan-out, so the PM
    auto-exited it. ``hermes_held`` must reach ``build_hermes_graph(..., held=...)``
    so the held-aware cap can keep it.
    """

    def test_hermes_held_reaches_build_hermes_graph(self, monkeypatch: pytest.MonkeyPatch) -> None:
        from digiquant.olympus.hermes import chain as chain_mod

        captured: dict[str, Any] = {}

        def _fake_build_hermes_graph(**kwargs: Any):
            captured.update(kwargs)

            class _Graph:
                def invoke(self, state: Any, *_a: Any, **_k: Any) -> Any:
                    return state

            return _Graph()

        # Stub the Atlas pass + telemetry so we exercise only the chain's Hermes wiring. The
        # Atlas stub populates one fresh segment so the #944 research-sufficiency gate passes
        # (a no-op Atlas pass would now correctly skip Hermes).
        def _atlas_produces_research(graph: Any, state: Any, *_a: Any, **_k: Any) -> Any:
            label = _a[-1] if _a else _k.get("label")
            if label == "atlas":
                from digiquant.olympus.atlas.state import SegmentPayload, SegmentSlot

                state.phase3_output = SegmentSlot(
                    payload=SegmentPayload(segment="macro", body={}, as_of=state.run_date)
                )
            return state

        monkeypatch.setattr(chain_mod, "_safe_invoke_graph", _atlas_produces_research)
        monkeypatch.setattr(chain_mod, "_run_terminal_phase", lambda *_a, **_k: _a[2])
        monkeypatch.setattr(chain_mod, "build_atlas_graph", lambda *_a, **_k: object())

        held = {"SPY", "IJR", "XLP"}
        with patch.object(chain_mod, "build_hermes_graph", _fake_build_hermes_graph):
            with simulated_pipeline(watchlist=("AAPL",)) as run:
                chain_mod.run_atlas_then_hermes(
                    atlas_input=AtlasInput(
                        run_date=date(2026, 6, 18),
                        watchlist=("AAPL", "SPY", "IJR", "XLP"),
                    ),
                    deps=chain_mod.ChainDeps(
                        atlas=run.deps,
                        hermes=run.hermes_deps,
                    ),
                    hermes_watchlist=["SPY", "IJR", "XLP", "AAPL"],
                    hermes_held=held,
                )

        assert "held" in captured, "build_hermes_graph called without held kwarg"
        assert set(captured["held"]) == held, (
            f"prior-book holdings not threaded into Hermes cap: {held - set(captured['held'])}"
        )
