"""Atlas → Hermes chain integration test.

Exercises :func:`digiquant.hermes.chain.run_atlas_then_hermes` end-to-end
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

import pytest

from digiquant.atlas.graph import AtlasInput

from digiquant.atlas.testing.simulator import simulated_pipeline


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
