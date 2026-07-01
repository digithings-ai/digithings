"""Unit tests for per-phase shared-context filtering (#696).

The unfiltered ``prior_context.latest_segments`` dump (every segment +
``analyst/*`` + ``pm-rebalance`` + digests) was serialized into all ~29 node
calls; nodes now declare the prior documents they actually consume.
"""

from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.phases._node_factory import _shared_context
from digiquant.olympus.atlas.phases.phase1_altdata import _SPECS as ALT_SPECS
from digiquant.olympus.atlas.phases.phase3_macro import _SPEC as MACRO_SPEC
from digiquant.olympus.atlas.phases.phase4_assetclass import _SPECS as ASSET_SPECS
from digiquant.olympus.atlas.state import AtlasResearchState, PriorContext

pytestmark = pytest.mark.unit


def _state() -> AtlasResearchState:
    segments = {
        key: {"date": "2026-06-11", "document_key": key, "doc_type": None, "payload": {"k": key}}
        for key in (
            "macro",
            "bonds",
            "equity",
            "sector-technology",
            "alt-sentiment-news",
            "analyst/NVDA",
            "pm-rebalance",
            "digest-delta",
        )
    }
    return AtlasResearchState(
        run_type="baseline",
        run_date=date(2026, 6, 12),
        prior_context=PriorContext(latest_segments=segments),
    )


def test_none_keeps_full_context() -> None:
    shared = _shared_context(_state())
    assert len(shared["prior_context"]["latest_segments"]) == 8


def test_filter_keeps_only_declared_keys() -> None:
    shared = _shared_context(_state(), context_keys=("bonds", "macro"))
    assert set(shared["prior_context"]["latest_segments"]) == {"bonds", "macro"}


def test_filter_excludes_decision_artifacts_from_research_nodes() -> None:
    shared = _shared_context(_state(), context_keys=("alt-sentiment-news",))
    segments = shared["prior_context"]["latest_segments"]
    assert "analyst/NVDA" not in segments
    assert "pm-rebalance" not in segments


def test_asset_class_specs_declare_macro_context() -> None:
    for spec in ASSET_SPECS:
        assert spec.extra_context_keys == ("macro",), spec.segment_slug


def test_macro_spec_declares_cross_asset_context() -> None:
    assert set(MACRO_SPEC.extra_context_keys) == {"bonds", "commodities", "forex", "equity"}


def test_alt_specs_default_to_own_slug_only() -> None:
    for spec in ALT_SPECS:
        assert spec.extra_context_keys == (), spec.segment_slug
