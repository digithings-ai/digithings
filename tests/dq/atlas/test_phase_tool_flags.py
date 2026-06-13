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
def test_alt_phases_grounding_modes():
    # alt-options-derivatives reads data tools (#708); every other alt-data
    # segment still grounds on soft signals (web/x search).
    by_slug = {s.segment_slug: s for s in ALT_SPECS}
    opts = by_slug["alt-options-derivatives"]
    assert opts.use_data_tools is True
    assert opts.live_search is False and opts.ai_portfolios is False
    # Every other alt-data segment still grounds on soft signals (web/x search),
    # never data tools.
    for spec in ALT_SPECS:
        if spec.segment_slug == "alt-options-derivatives":
            continue
        assert spec.use_data_tools is False, spec.segment_slug
        assert spec.live_search or spec.ai_portfolios, spec.segment_slug
    # alt-ai-portfolios is the x_search one; the rest use web_search.
    assert by_slug["alt-ai-portfolios"].ai_portfolios is True
    assert by_slug["alt-ai-portfolios"].live_search is False
    assert by_slug["alt-sentiment-news"].live_search is True


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
def test_options_segment_makes_no_paid_search(monkeypatch):
    # Phase D PR-1 (#708): with use_data_tools=True and live_search=False, the
    # options segment must never fire a paid web_search — web_grounding is None
    # regardless of whether the Supabase client is available.
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)

    def _fail(**_k):  # a paid web_search call here would be the bug
        raise AssertionError("options segment must not call fetch_web_grounding")

    monkeypatch.setattr("digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding", _fail)
    _tools, _execute, grounding = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=False,
        run_date=date(2026, 6, 8),
        model="xai/grok-4.3",
        segment="alt-options-derivatives",
    )
    assert grounding is None


@pytest.mark.unit
def test_macro_series_yaml_has_volatility_complex():
    # The FRED vol series alt-options-derivatives reads must be in the manifest.
    import yaml

    from digiquant.olympus.atlas.graph import _atlas_config_root

    raw = yaml.safe_load((_atlas_config_root() / "macro_series.yaml").read_text())
    ids = {s["id"] for s in raw["fred"]["series"]}
    assert {"VIXCLS", "VXVCLS", "VXNCLS", "GVZCLS", "OVXCLS"} <= ids


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
