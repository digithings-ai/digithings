from __future__ import annotations

from datetime import date

import pytest

from digiquant.olympus.atlas.phases import _node_factory
from digiquant.olympus.atlas.phases.phase1_altdata import _SPECS as ALT_SPECS
from digiquant.olympus.atlas.phases.phase2_institutional import _SPECS as INST_SPECS
from digiquant.olympus.atlas.phases.phase3_macro import _SPEC as MACRO
from digiquant.olympus.atlas.phases.phase4_assetclass import _SPECS as ASSET_SPECS


@pytest.mark.unit
def test_macro_uses_data_tools_and_search():
    assert MACRO.use_data_tools is True
    assert MACRO.live_search is True  # intl-M2 fallback


@pytest.mark.unit
def test_alt_phases_use_live_search_only():
    for spec in ALT_SPECS:
        assert spec.live_search is True, spec.segment_slug
        assert spec.use_data_tools is False, spec.segment_slug


@pytest.mark.unit
def test_inst_phases_use_live_search_only():
    for spec in INST_SPECS:
        assert spec.live_search is True, spec.segment_slug
        assert spec.use_data_tools is False, spec.segment_slug


@pytest.mark.unit
def test_asset_classes_use_data_tools():
    for spec in ASSET_SPECS:
        assert spec.use_data_tools is True, spec.segment_slug
    # International also web-searches for non-US market/M2 freshness.
    intl = next(s for s in ASSET_SPECS if s.segment_slug == "international")
    assert intl.live_search is True


@pytest.mark.unit
def test_build_grounding_respects_kill_switch(monkeypatch):
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    monkeypatch.setattr(
        "digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding",
        lambda **_k: {"summary": "x", "sources": [], "as_of": "2026-06-08"},
    )
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "0")
    tools, execute_tool, grounding = _node_factory.build_grounding(
        use_data_tools=True, live_search=True, run_date=date(2026, 6, 8), model="xai/grok-4.3"
    )
    assert tools is None and execute_tool is None and grounding is None

    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    tools, execute_tool, grounding = _node_factory.build_grounding(
        use_data_tools=True, live_search=True, run_date=date(2026, 6, 8), model="xai/grok-4.3"
    )
    assert tools is not None and execute_tool is not None and grounding is not None


@pytest.mark.unit
def test_build_grounding_degrades_when_client_unavailable(monkeypatch):
    # A missing/broken Supabase client must not crash the phase: data tools are
    # dropped, but web grounding (which needs no Supabase client) still works.
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.setattr(
        "digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding",
        lambda **_k: {"summary": "x", "sources": [], "as_of": "2026-06-08"},
    )

    def _boom():
        raise RuntimeError("supabase not configured")

    monkeypatch.setattr(_node_factory, "_atlas_data_client", _boom)
    tools, execute_tool, grounding = _node_factory.build_grounding(
        use_data_tools=True, live_search=True, run_date=date(2026, 6, 8), model="xai/grok-4.3"
    )
    assert tools is None and execute_tool is None
    assert grounding is not None  # web grounding unaffected
