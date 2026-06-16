"""Tests for WS3a additions to Phase 7 synthesis and Phase 6 consolidate.

Covers:
- DigestSnapshot.regime_label field presence and defaults.
- Deterministic regime_label backfill from phase3 when LLM omits it.
- LLM-emitted regime_label is preserved when non-empty.
- fed_odds wiring: preflight market_context → phase6 bias row → phase7 phase_inputs.
"""

from __future__ import annotations

import json
from datetime import date
from typing import Any  # noqa  # scored-lint: heterogeneous FakeSupabase fixture / kwargs dicts
from unittest.mock import patch

import pytest

from digigraph.graph.pipeline_builder import build_pipeline

from digiquant.olympus.atlas.phases.phase6_consolidate import build_phase6
from digiquant.olympus.atlas.phases.phase7_synthesis import (
    DigestSnapshot,
    _regime_label_from_phase3,
    build_phase7,
)
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    Carried,
    DataLayerSnapshot,
    SegmentPayload,
    SegmentSlot,
)

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


# ─── Helpers ────────────────────────────────────────────────────────────────


def _slot(slug: str, bias: str = "bullish", **extra: Any) -> SegmentSlot:
    body = {"segment": slug, "bias": bias, **extra}
    return SegmentSlot(payload=SegmentPayload(segment=slug, body=body, as_of=date(2026, 4, 26)))


def _base_state(regime_label: str = "Risk-on / Policy easing") -> AtlasResearchState:
    """Minimal state seeded through phase 5 with an optional regime_label in phase3."""
    state = AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 4, 26),
        config=AtlasConfigBundle(watchlist=["AAPL"]),
    )
    state.phase1_outputs = {
        "alt-cta-positioning": _slot("alt-cta-positioning", bias="neutral"),
        "alt-options-derivatives": _slot("alt-options-derivatives", vix_level=14.5),
    }
    state.phase2_outputs = {
        "inst-institutional-flows": _slot("inst-institutional-flows"),
        "inst-hedge-fund-intel": _slot("inst-hedge-fund-intel"),
    }
    state.phase3_output = _slot("macro", regime_label=regime_label)
    state.phase4_outputs = {
        "bonds": _slot("bonds"),
        "commodities": _slot("commodities"),
        "forex": _slot("forex"),
        "crypto": _slot("crypto"),
    }
    state.phase5_outputs = {"equity": _slot("equity")}
    return state


def _digest_json(regime_label: str = "") -> str:
    """Build a minimal DigestSnapshot-shaped JSON the fake LLM returns."""
    return json.dumps(
        {
            "segment": "master-digest",
            "date": "2026-04-26",
            "bias": "neutral",
            "headline": "Late-cycle consolidation; policy easing priced.",
            "material_findings": [],
            "sources": [],
            "notes": "",
            "market_regime_snapshot": "Growth slowing, policy easing.",
            "alt_data_dashboard": "CTAs neutral.",
            "institutional_summary": "Modest inflows.",
            "asset_classes_summary": "Bonds rallying.",
            "us_equities_summary": "Narrow breadth.",
            "thesis_tracker": "",
            "portfolio_recommendations": "",
            "actionable_summary": [],
            "risk_radar": [],
            "segment_freshness": {},
            # regime_label intentionally absent (or supplied below) per test scenario.
            "regime_label": regime_label,
        }
    )


# ─── DigestSnapshot model-level tests ────────────────────────────────────────


@pytest.mark.unit
class TestDigestSnapshotField:
    def test_regime_label_has_default_empty(self) -> None:
        """regime_label must be optional with a default of ''."""
        snapshot = DigestSnapshot(
            segment="master-digest",
            date=date(2026, 4, 26),
            bias="neutral",
            headline="Test",
            market_regime_snapshot="x",
            alt_data_dashboard="y",
            institutional_summary="z",
            asset_classes_summary="a",
            us_equities_summary="b",
        )
        assert snapshot.regime_label == ""

    def test_regime_label_round_trips(self) -> None:
        snapshot = DigestSnapshot(
            segment="master-digest",
            date=date(2026, 4, 26),
            bias="neutral",
            headline="Test",
            market_regime_snapshot="x",
            alt_data_dashboard="y",
            institutional_summary="z",
            asset_classes_summary="a",
            us_equities_summary="b",
            regime_label="Risk-off / Stagflation watch",
        )
        dumped = snapshot.model_dump(mode="json")
        assert dumped["regime_label"] == "Risk-off / Stagflation watch"


# ─── Deterministic backfill tests ────────────────────────────────────────────


@pytest.mark.unit
class TestRegimeLabelBackfill:
    def test_backfill_from_phase3_when_llm_emits_empty(self) -> None:
        """When LLM returns regime_label='', we backfill from phase3 body."""
        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        state = _base_state(regime_label="Neutral / Rate plateau")

        with patch(
            "digigraph.graph.research_agent.completion_text",
            return_value=_digest_json(regime_label=""),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert final.phase7_digest is not None
        # LLM gave empty string → deterministic backfill from phase3.
        assert final.phase7_digest["regime_label"] == "Neutral / Rate plateau"

    def test_llm_emitted_regime_label_preserved(self) -> None:
        """When LLM emits a non-empty regime_label, it is preserved as-is."""
        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        state = _base_state(regime_label="Risk-on / Policy easing")

        with patch(
            "digigraph.graph.research_agent.completion_text",
            return_value=_digest_json(regime_label="Risk-on / Early recovery"),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert final.phase7_digest is not None
        # LLM supplied a non-empty value → keep it.
        assert final.phase7_digest["regime_label"] == "Risk-on / Early recovery"

    def test_backfill_falls_back_to_empty_when_phase3_absent(self) -> None:
        """No phase3 output → regime_label stays empty string (no crash)."""
        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        state = _base_state()
        state.phase3_output = None  # no macro phase this run

        with patch(
            "digigraph.graph.research_agent.completion_text",
            return_value=_digest_json(regime_label=""),
        ):
            result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        assert final.phase7_digest is not None
        assert final.phase7_digest["regime_label"] == ""

    def test_regime_label_from_phase3_helper_returns_empty_on_none(self) -> None:
        """Unit-test the private helper directly."""
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        assert _regime_label_from_phase3(state) == ""

    def test_regime_label_from_phase3_helper_skips_carry_slots(self) -> None:
        """Carry slots (source='carried') must not feed the backfill."""
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 4, 26))
        # Simulate a carry slot: SegmentSlot with a Carried payload (delta run carry-forward).
        state.phase3_output = SegmentSlot(
            payload=Carried(
                baseline_date=date(2026, 4, 25),
                reason="below_triage_threshold",
            )
        )
        assert _regime_label_from_phase3(state) == ""


# ─── fed_odds wiring tests ────────────────────────────────────────────────────


def _fed_odds_rows() -> list[dict[str, Any]]:
    """Canned macro_series_observations rows for the FakeSupabaseClient."""
    return [
        {
            "source": "kalshi",
            "series_id": "FEDPROB/2026-06-17/upper_gt_3.75",
            "obs_date": "2026-06-16",
            "value": 0.6,
            "meta": {},
        },
        {
            "source": "kalshi",
            "series_id": "FEDPROB/2026-06-17/upper_gt_4",
            "obs_date": "2026-06-16",
            "value": 0.4,
            "meta": {},
        },
        {
            "source": "polymarket",
            "series_id": "FEDPROB/2026-06-17/pm/will-the-fed-hold",
            "obs_date": "2026-06-16",
            "value": 0.7,
            "meta": {"question": "Will the Fed hold?"},
        },
    ]


@pytest.mark.unit
class TestFedOddsWiring:
    def _preflight_deps(self, fed_rows: list[dict[str, Any]]) -> Any:
        """Build PreflightDeps backed by a FakeSupabaseClient with canned fed rows."""
        from digiquant.olympus.atlas.phases.preflight import PreflightDeps

        client = FakeSupabaseClient(
            canned_reads={
                "daily_snapshots": [],
                "documents": [],
                "price_technicals": [{"date": "2026-06-16", "ticker": "SPY"}],
                "macro_series_observations": fed_rows,
            }
        )
        return PreflightDeps(
            client=client,
            config_loader=lambda: AtlasConfigBundle(),
        )

    def test_fed_odds_populated_in_market_context(self) -> None:
        """When macro_series_observations has FEDPROB rows, market_context['fed_odds'] is set."""
        from digiquant.olympus.atlas.phases.preflight import build_preflight_node

        deps = self._preflight_deps(_fed_odds_rows())
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 6, 16))
        out = node(state)
        mc = out["data_layer"].market_context
        assert "fed_odds" in mc, "fed_odds must appear in market_context when rows exist"
        assert mc["fed_odds"]["meeting_date"] == "2026-06-17"

    def test_fed_odds_absent_when_no_rows(self) -> None:
        """No FEDPROB rows → fed_odds must NOT appear in market_context (not even None)."""
        from digiquant.olympus.atlas.phases.preflight import build_preflight_node

        deps = self._preflight_deps([])
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 6, 16))
        out = node(state)
        # Empty result from get_fed_rate_probabilities → fed_odds not added to market_context.
        assert "fed_odds" not in out["data_layer"].market_context

    def test_fed_odds_fail_soft_on_db_error(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """A database error in get_fed_rate_probabilities must not crash preflight."""
        from digiquant.olympus.atlas.phases.preflight import build_preflight_node
        import digiquant.olympus.atlas.phases.preflight as pf_mod

        deps = self._preflight_deps([])
        node = build_preflight_node(deps)
        state = AtlasResearchState(run_type="baseline", run_date=date(2026, 6, 16))

        with patch.object(
            pf_mod,
            "get_fed_rate_probabilities",
            side_effect=OSError("connection reset"),
        ):
            out = node(state)
        # Preflight completed normally; fed_odds is absent (not None, not raised).
        assert "fed_odds" not in out["data_layer"].market_context

    def test_fed_odds_reaches_phase6_bias_row(self) -> None:
        """fed_odds flows from market_context through phase6 into the bias row."""
        # Build state as if preflight ran and injected fed_odds into data_layer.
        state = _base_state()
        fed_odds_payload = {
            "meeting_date": "2026-06-17",
            "most_likely": "3.5",
            "distribution": {"<=3.25": 0.03, "3.5": 0.17, ">4.25": 0.20},
            "sources": ["kalshi"],
        }
        state.data_layer = DataLayerSnapshot(
            market_context={"fed_odds": fed_odds_payload},
        )

        compiled = build_pipeline(AtlasResearchState, [build_phase6()])
        result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        row = final.phase6_bias_row
        assert row is not None
        # fed_odds must be propagated into the bias row (not None).
        assert row["fed_odds"] is not None
        assert row["fed_odds"]["meeting_date"] == "2026-06-17"

    def test_fed_odds_none_when_market_context_empty(self) -> None:
        """No fed_odds in market_context → bias row fed_odds is None (fail-soft)."""
        state = _base_state()
        # data_layer with empty market_context (default).
        state.data_layer = DataLayerSnapshot(market_context={})

        compiled = build_pipeline(AtlasResearchState, [build_phase6()])
        result = compiled.invoke(state)
        final = AtlasResearchState.model_validate(result) if isinstance(result, dict) else result

        row = final.phase6_bias_row
        assert row is not None
        assert row["fed_odds"] is None

    def test_fed_odds_in_phase7_digest_phase_inputs(self) -> None:
        """fed_odds from bias_row must be visible to the LLM via phase_inputs.bias_row."""
        state = _base_state()
        fed_odds_payload = {
            "meeting_date": "2026-06-17",
            "most_likely": "3.5",
            "distribution": {"<=3.25": 0.03},
            "sources": ["kalshi"],
        }
        state.data_layer = DataLayerSnapshot(market_context={"fed_odds": fed_odds_payload})

        compiled = build_pipeline(AtlasResearchState, [build_phase6(), build_phase7()])
        captured_inputs: list[dict[str, Any]] = []

        def fake_completion(_m: str, msgs: list[dict[str, Any]], **_: Any) -> str:
            # Extract the PHASE_INPUTS block that was passed to the LLM.
            for part in msgs[1]["content"]:
                if isinstance(part, dict) and part.get("text", "").startswith("PHASE_INPUTS"):
                    body = json.loads(part["text"].split(":", 1)[1].strip())
                    captured_inputs.append(body)
                    break
            return _digest_json(regime_label="")

        with patch("digigraph.graph.research_agent.completion_text", side_effect=fake_completion):
            compiled.invoke(state)

        assert captured_inputs, "LLM must have been called"
        bias_row = captured_inputs[0].get("bias_row", {})
        assert bias_row.get("fed_odds") is not None, (
            "fed_odds must appear in bias_row passed to Phase 7 LLM"
        )
        assert bias_row["fed_odds"]["meeting_date"] == "2026-06-17"
