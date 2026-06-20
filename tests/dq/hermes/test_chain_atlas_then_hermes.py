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
  outputs (phase7c_analysts, phase7d_rebalance, phase9_evolution) by the
  end. The fake Supabase client should record exactly one daily_snapshots
  upsert and the analyst/PM document writes.
- ``test_monthly_chain_short_circuits_at_atlas`` — monthly run uses
  Atlas's phase_monthly path; Hermes does not run; state's H-slots stay
  unset.
"""

from __future__ import annotations

from datetime import date
from typing import Any
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
                    run_type="baseline",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )

        # Research outputs (Atlas).
        assert final.phase7_digest is not None
        assert "master-digest" in (final.phase7_digest.get("segment") or "")

        # Analysis outputs (Hermes).
        assert "AAPL" in final.phase7c_analysts, (
            "Hermes phase7c should have populated phase7c_analysts"
        )
        assert final.phase7d_rebalance is not None, (
            "Hermes phase7d should have populated phase7d_rebalance"
        )
        # phase9_evolution lands when phase9 deps are wired.
        assert final.phase9_evolution is not None, (
            "Hermes phase9 should have populated phase9_evolution when deps=Phase9Deps(...)"
        )

    def test_baseline_chain_publish_writes_after_hermes(self) -> None:
        """Terminal publish runs once with both engines' outputs in scope."""
        with simulated_pipeline(watchlist=("AAPL",), phase9=True) as run:
            final = run.invoke(
                AtlasInput(
                    run_type="baseline",
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
        assert "AAPL" in final.phase7c_analysts


@pytest.mark.unit
class TestChainMaterialization:
    def test_pm_decision_materializes_positions_and_nav(self) -> None:
        """Phase 9D writes the PM book to positions + base-100 NAV (#700)."""
        rebalance = {
            "recommended_portfolio": [{"ticker": "AAPL", "target_pct": 100}],
            "actions": [],
            "notes": "synthetic",
        }
        with simulated_pipeline(
            watchlist=("AAPL",),
            phase9=True,
            overrides={"RebalanceDecision": rebalance},
        ) as run:
            final = run.invoke(
                AtlasInput(run_type="baseline", run_date=date(2026, 4, 26), watchlist=("AAPL",))
            )

        assert final.phase7d_rebalance is not None
        store = run.client.store
        positions = {r["ticker"]: r for r in store.get("positions", [])}
        assert positions["AAPL"]["weight_pct"] == 100.0
        navs = store.get("nav_history", [])
        assert len(navs) == 1
        assert navs[0]["nav"] == 100.0  # first-ever run seeds the index at 100

    def test_materialize_off_writes_no_book(self) -> None:
        with simulated_pipeline(
            watchlist=("AAPL",),
            phase9=True,
            materialize=False,
            overrides={
                "RebalanceDecision": {
                    "recommended_portfolio": [{"ticker": "AAPL", "target_pct": 100}],
                    "actions": [],
                    "notes": "x",
                }
            },
        ) as run:
            run.invoke(
                AtlasInput(run_type="baseline", run_date=date(2026, 4, 26), watchlist=("AAPL",))
            )
        assert "positions" not in run.client.store
        assert "nav_history" not in run.client.store


@pytest.mark.unit
class TestChainMonthly:
    def test_monthly_chain_short_circuits_at_atlas(self) -> None:
        """Monthly runs end at Atlas's phase_monthly; Hermes does not run."""
        # Monthly does not use phase9 deps, has no Hermes wiring.
        with simulated_pipeline(watchlist=("AAPL",)) as run:
            final = run.invoke(
                AtlasInput(
                    run_type="monthly",
                    run_date=date(2026, 4, 26),
                    watchlist=("AAPL",),
                )
            )

        # Atlas's phase_monthly populates phase7_digest with the monthly shape.
        assert final.phase7_digest is not None

        # Hermes-side slots stay empty/None — phase7c/7cd/7d/9 did not run.
        assert final.phase7c_analysts == {}, "monthly chain should not invoke Hermes phase7c"
        assert final.phase7d_rebalance is None, "monthly chain should not invoke Hermes phase7d"
        assert final.phase9_evolution is None, "monthly chain should not invoke Hermes phase9"


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

        # Stub the Atlas pass + telemetry so we exercise only the chain's Hermes wiring.
        monkeypatch.setattr(chain_mod, "_safe_invoke_graph", lambda graph, state, *_a, **_k: state)
        monkeypatch.setattr(chain_mod, "_run_terminal_phase", lambda *_a, **_k: _a[2])
        monkeypatch.setattr(chain_mod, "build_atlas_graph", lambda *_a, **_k: object())

        held = {"SPY", "IJR", "XLP"}
        with patch.object(chain_mod, "build_hermes_graph", _fake_build_hermes_graph):
            with simulated_pipeline(watchlist=("AAPL",)) as run:
                chain_mod.run_atlas_then_hermes(
                    atlas_input=AtlasInput(
                        run_type="baseline",
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
