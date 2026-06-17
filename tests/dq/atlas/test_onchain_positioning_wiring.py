"""Wiring tests for the on-chain cohort-positioning signal (#801).

Covers the full fed_odds-style path:
- preflight: provider result → market_context['onchain_positioning'] + persisted rows.
- preflight fail-soft: empty/errored result or a provider exception leaves it absent, no crash.
- phase6: market_context → bias_row['onchain_positioning'].
- phase7: bias_row['onchain_positioning'] reaches the digest LLM's phase_inputs.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa  # scored-lint: heterogeneous fixture / kwargs dicts
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.data.onchain.hyperdash import CohortPositioning, cohort_summary_to_positioning
from digiquant.olympus.atlas.phases.phase6_consolidate import build_phase6
from digiquant.olympus.atlas.phases.phase7_synthesis import build_phase7
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DataLayerSnapshot,
    SegmentPayload,
    SegmentSlot,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


def _slot(slug: str, bias: str = "bullish", **extra: Any) -> SegmentSlot:
    body = {"segment": slug, "bias": bias, **extra}
    return SegmentSlot(payload=SegmentPayload(segment=slug, body=body, as_of=date(2026, 4, 26)))


def _base_state() -> AtlasResearchState:
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )
    state.phase1_outputs = {
        "alt-options-derivatives": _slot("alt-options-derivatives", vix_level=14.5)
    }
    state.phase3_output = _slot("macro", regime_label="Risk-on / Policy easing")
    state.phase4_outputs = {"crypto": _slot("crypto")}
    state.phase5_outputs = {"equity": _slot("equity")}
    return state


def _canned_positioning() -> CohortPositioning:
    """Smart cohort net-short ETH, crowd net-long ETH → divergence -0.8 (the live-validated read)."""
    summary = {
        "timestamp": "2026-04-26T00:00:00Z",
        "totalTraders": 999,
        "pnlCohorts": [
            {
                "id": "extremely_profitable",
                "longNotional": 1_000_000,
                "shortNotional": 4_000_000,
                "topMarkets": [
                    {"ticker": "ETH", "longNotional": 100_000, "shortNotional": 900_000}
                ],
            },
            {
                "id": "rekt",
                "longNotional": 5_000_000,
                "shortNotional": 1_000_000,
                "topMarkets": [
                    {"ticker": "ETH", "longNotional": 900_000, "shortNotional": 100_000}
                ],
            },
        ],
    }
    return cohort_summary_to_positioning(summary)


@pytest.mark.unit
class TestPreflightOnchain:
    def _deps(self) -> Any:
        from digiquant.olympus.atlas.phases.preflight import PreflightDeps

        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-04-26", "ticker": "SPY"}],
                "macro_series_observations": [],
            }
        )
        return PreflightDeps(client=client, config_loader=AtlasConfigBundle)

    def test_populates_market_context_and_persists_rows(self) -> None:
        import digiquant.olympus.atlas.phases.preflight as pf_mod
        from digiquant.olympus.atlas.phases.preflight import build_preflight_node

        deps = self._deps()
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch.object(pf_mod, "get_onchain_cohort_positioning", lambda: _canned_positioning()):
            out = node(state)

        mc = out["data_layer"].market_context
        assert "onchain_positioning" in mc
        assert mc["onchain_positioning"]["overall_divergence"] == pytest.approx(
            0.2 - 5 / 6, abs=1e-4
        )
        # Per-market rows were persisted for backtest history.
        rows = deps.client.store.get("onchain_cohort_positioning", [])
        assert any(r["market"] == "ETH" for r in rows)
        assert all(r["_on_conflict"] == "date,market" for r in rows)

    def test_absent_when_provider_returns_empty(self) -> None:
        import digiquant.olympus.atlas.phases.preflight as pf_mod
        from digiquant.olympus.atlas.phases.preflight import build_preflight_node

        node = build_preflight_node(self._deps())
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch.object(pf_mod, "get_onchain_cohort_positioning", CohortPositioning.empty):
            out = node(state)
        assert "onchain_positioning" not in out["data_layer"].market_context

    def test_fail_soft_on_provider_exception(self) -> None:
        import digiquant.olympus.atlas.phases.preflight as pf_mod
        from digiquant.olympus.atlas.phases.preflight import build_preflight_node

        def _boom() -> CohortPositioning:
            raise OSError("hyperdash unreachable")

        node = build_preflight_node(self._deps())
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        with patch.object(pf_mod, "get_onchain_cohort_positioning", _boom):
            out = node(state)  # must not raise
        assert "onchain_positioning" not in out["data_layer"].market_context


@pytest.mark.unit
class TestOnchainBiasRow:
    def test_reaches_phase6_bias_row(self) -> None:
        state = _base_state()
        compact = _canned_positioning().compact_summary()
        state.data_layer = DataLayerSnapshot(market_context={"onchain_positioning": compact})

        compiled = build_pipeline(AtlasResearchState, [build_phase6()])
        result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        row = final.phase6_bias_row
        assert row is not None
        assert row["onchain_positioning"] is not None
        assert row["onchain_positioning"]["top_divergent_markets"][0]["market"] == "ETH"

    def test_none_when_market_context_empty(self) -> None:
        state = _base_state()
        state.data_layer = DataLayerSnapshot(market_context={})
        compiled = build_pipeline(AtlasResearchState, [build_phase6()])
        result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result
        assert final.phase6_bias_row is not None
        assert final.phase6_bias_row["onchain_positioning"] is None

    def test_reaches_phase7_digest_phase_inputs(self) -> None:
        state = _base_state()
        compact = _canned_positioning().compact_summary()
        state.data_layer = DataLayerSnapshot(market_context={"onchain_positioning": compact})

        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        captured: list[dict[str, Any]] = []

        def fake_completion(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            for part in msgs[1]["content"]:
                if isinstance(part, dict) and part.get("text", "").startswith("PHASE_INPUTS"):
                    captured.append(json.loads(part["text"].split(":", 1)[1].strip()))
                    break
            return json.dumps(
                {
                    "segment": "master-digest",
                    "date": "2026-04-26",
                    "bias": "neutral",
                    "headline": "x",
                    "material_findings": [],
                    "sources": [],
                    "notes": "",
                    "market_regime_snapshot": "x",
                    "alt_data_dashboard": "y",
                    "institutional_summary": "z",
                    "asset_classes_summary": "a",
                    "us_equities_summary": "b",
                    "regime_label": "",
                }
            )

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake_completion):
            compiled.invoke(state)

        assert captured, "LLM must have been called"
        bias_row = captured[0].get("bias_row", {})
        assert bias_row.get("onchain_positioning") is not None
        assert bias_row["onchain_positioning"]["top_divergent_markets"][0]["market"] == "ETH"
