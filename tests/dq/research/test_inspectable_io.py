"""WP-B: inspectable Inputs + bias-row documents published from Atlas state."""

from __future__ import annotations

from datetime import date

import pytest
from digiquant.olympus.atlas.inspectable_io import (
    BIAS_ROW_DOCUMENT_KEY,
    INPUTS_DOCUMENT_KEY,
    build_bias_row_payload,
    build_inputs_payload,
    render_bias_row_markdown,
    render_inputs_markdown,
)
from digiquant.olympus.atlas.phases.publish_phase import PublishDeps, build_publish_node
from digiquant.olympus.atlas.state import (
    AtlasConfigBundle,
    AtlasResearchState,
    DataLayerSnapshot,
    PriorContext,
)
from digiquant.olympus.tenancy import house_workspace_id

from tests.dq.atlas.test_supabase_io import FakeSupabaseClient


def _state_with_inputs() -> AtlasResearchState:
    return AtlasResearchState(
        run_type="delta",
        run_date=date(2026, 8, 31),
        config=AtlasConfigBundle(
            watchlist=["SPY", "QQQ", "GLD"],
            investment_profile={"horizon": "long"},
            preferences={"max_name_pct": 12},
            profile_config_version_id="11111111-1111-1111-1111-111111111111",
        ),
        data_layer=DataLayerSnapshot(
            price_technicals_latest=date(2026, 8, 29),
            price_technicals_ticker_count=40,
            macro_series_latest=date(2026, 8, 28),
            fallback_used="supabase",
            stale_price=False,
            stale_macro=False,
            price_basket_gap=["FXI"],
        ),
        prior_context=PriorContext(
            last_snapshots=[{"date": "2026-08-28", "snapshot": {}}],
            latest_segments={"macro": {"date": "2026-08-28"}},
            active_theses=[{"thesis_id": "geo-gold"}],
            prior_book=[{"ticker": "SPY", "weight": 0.1}],
        ),
    )


@pytest.mark.unit
class TestInputsPayload:
    def test_payload_is_pydantic_envelope_with_watchlist_and_freshness(self) -> None:
        payload = build_inputs_payload(_state_with_inputs())
        dumped = payload.model_dump(mode="json")
        assert dumped["doc_type"] == "inputs"
        assert dumped["date"] == "2026-08-31"
        assert dumped["watchlist"] == ["SPY", "QQQ", "GLD"]
        assert dumped["profile"]["profile_config_version_id"] == (
            "11111111-1111-1111-1111-111111111111"
        )
        assert dumped["profile"]["preferences_digest"]
        assert dumped["profile"]["investment_profile_digest"]
        assert dumped["market_data"]["price_technicals_latest"] == "2026-08-29"
        assert dumped["market_data"]["macro_series_latest"] == "2026-08-28"
        assert dumped["market_data"]["stale_price"] is False
        assert dumped["market_data"]["price_basket_gap"] == ["FXI"]
        assert dumped["prior_context"]["last_snapshot_date"] == "2026-08-28"
        assert dumped["prior_context"]["active_theses_count"] == 1
        assert dumped["prior_context"]["latest_segment_dates"]["macro"] == "2026-08-28"

    def test_markdown_is_a_short_readable_table(self) -> None:
        md = render_inputs_markdown(build_inputs_payload(_state_with_inputs()))
        assert "# Inputs 2026-08-31" in md
        assert "SPY" in md
        assert "2026-08-29" in md


@pytest.mark.unit
class TestBiasRowPayload:
    def test_payload_formats_deterministic_row(self) -> None:
        row = {
            "date": "2026-08-31",
            "run_type": "delta",
            "macro_regime": "Slowing",
            "equity_bias": "bullish",
            "crypto_bias": "neutral",
            "bond_bias": "bearish",
            "commodity_bias": "bullish",
            "forex_bias": "",
            "vix_level": 15.2,
            "inst_flow": "inflow",
            "options_sentiment": "mixed",
            "cta_direction": "long",
            "hf_consensus": "neutral",
            "fed_odds": {"meeting_date": "2026-09-17", "most_likely": "hold"},
            "onchain_positioning": {"overall_divergence": 0.4},
            "notes": "carry from quiet triage",
        }
        payload = build_bias_row_payload(row)
        dumped = payload.model_dump(mode="json")
        assert dumped["doc_type"] == "bias_row"
        assert dumped["macro_regime"] == "Slowing"
        assert dumped["equity_bias"] == "bullish"
        assert dumped["vix_level"] == 15.2
        assert dumped["notes"] == "carry from quiet triage"

    def test_markdown_is_a_short_table_plus_notes(self) -> None:
        payload = build_bias_row_payload(
            {
                "date": "2026-08-31",
                "run_type": "delta",
                "macro_regime": "Slowing",
                "equity_bias": "bullish",
                "notes": "VIX still compressed.",
            }
        )
        md = render_bias_row_markdown(payload)
        assert "# Bias row 2026-08-31" in md
        assert "Slowing" in md
        assert "VIX still compressed." in md


@pytest.mark.unit
class TestPublishPhaseInspectableDocs:
    def test_publish_writes_inputs_and_bias_row(self) -> None:
        client = FakeSupabaseClient()
        state = _state_with_inputs()
        state.phase6_bias_row = {
            "date": "2026-08-31",
            "run_type": "delta",
            "macro_regime": "Slowing",
            "equity_bias": "bullish",
            "notes": "",
        }
        node = build_publish_node(PublishDeps(client=client))
        node(state)

        by_key = {row["document_key"]: row for row in client.store["documents"]}
        assert INPUTS_DOCUMENT_KEY in by_key
        assert BIAS_ROW_DOCUMENT_KEY in by_key
        inputs = by_key[INPUTS_DOCUMENT_KEY]
        assert inputs["payload"]["doc_type"] == "inputs"
        assert inputs["payload"]["watchlist"] == ["SPY", "QQQ", "GLD"]
        assert inputs["workspace_id"] == str(house_workspace_id())
        assert inputs["content"]
        bias = by_key[BIAS_ROW_DOCUMENT_KEY]
        assert bias["payload"]["doc_type"] == "bias_row"
        assert bias["payload"]["macro_regime"] == "Slowing"
        assert "Slowing" in (bias["content"] or "")

    def test_missing_bias_row_does_not_block_inputs(self) -> None:
        client = FakeSupabaseClient()
        node = build_publish_node(PublishDeps(client=client))
        node(_state_with_inputs())
        keys = {row["document_key"] for row in client.store["documents"]}
        assert INPUTS_DOCUMENT_KEY in keys
        assert BIAS_ROW_DOCUMENT_KEY not in keys
