from __future__ import annotations

from datetime import date, datetime

import pytest

from digiquant.olympus.atlas.phases import _node_factory
from digiquant.olympus.atlas.phases.phase1_altdata import _SPECS as ALT_SPECS
from digiquant.olympus.atlas.phases.phase2_institutional import _SPECS as INST_SPECS
from digiquant.olympus.atlas.phases.phase3_macro import _SPEC as MACRO
from digiquant.olympus.atlas.phases.phase4_assetclass import _SPECS as ASSET_SPECS


@pytest.mark.unit
def test_macro_uses_data_tools_and_fallback_search():
    assert MACRO.use_data_tools is True
    assert MACRO.live_search is True
    # #711: macro's web_search is now a stale-only paid fallback, not a daily input.
    assert MACRO.live_search_is_fallback is True


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
        use_data_tools=True,
        live_search=True,
        run_date=date(2026, 6, 8),
        model="openrouter/openrouter/auto",
    )
    assert tools is None and execute_tool is None and grounding is None

    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    tools, execute_tool, grounding = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=True,
        run_date=date(2026, 6, 8),
        model="openrouter/openrouter/auto",
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
        model="openrouter/openrouter/auto",
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
        use_data_tools=True,
        live_search=True,
        run_date=date(2026, 6, 8),
        model="openrouter/openrouter/auto",
    )
    assert tools is None and execute_tool is None
    assert grounding is not None  # web grounding unaffected


# --- Phase D #711: ingested-first / paid-on-stale macro fallback -------------


def _stub_freshness(monkeypatch, value):
    """Point query_macro_series_freshness at a canned date / None / raiser."""
    if isinstance(value, BaseException) or (
        isinstance(value, type) and issubclass(value, BaseException)
    ):

        def _impl(**_k):
            raise value if isinstance(value, BaseException) else value()
    else:

        def _impl(**_k):
            return value

    monkeypatch.setattr("digiquant.olympus.atlas.supabase_io.query_macro_series_freshness", _impl)


@pytest.mark.unit
def test_macro_fallback_skips_paid_search_when_layer_fresh(monkeypatch):
    # Fresh ingested FRED layer → the fallback web_search must NOT fire; the
    # segment grounds on data tools alone. This is the Phase D cost cut.
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.delenv("ATLAS_MACRO_STALE_DAYS", raising=False)
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 6, 12))  # 1 day stale → fresh

    def _fail(**_k):
        raise AssertionError("fresh ingested layer must not fire the paid fallback web_search")

    monkeypatch.setattr("digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding", _fail)
    _tools, _execute, grounding = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=True,
        live_search_is_fallback=True,
        run_date=date(2026, 6, 13),
        model="openrouter/openrouter/auto",
        segment="macro",
    )
    assert grounding is None


@pytest.mark.unit
def test_macro_fallback_fires_paid_search_when_layer_stale(monkeypatch):
    # Stale ingested layer (older than the window) → fall through to paid search.
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.delenv("ATLAS_MACRO_STALE_DAYS", raising=False)
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 5, 1))  # >7 days stale
    monkeypatch.setattr(
        "digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding",
        lambda **_k: {"summary": "fallback", "sources": [], "as_of": "2026-06-13"},
    )
    _tools, _execute, grounding = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=True,
        live_search_is_fallback=True,
        run_date=date(2026, 6, 13),
        model="openrouter/openrouter/auto",
        segment="macro",
    )
    assert grounding is not None and grounding["summary"] == "fallback"


@pytest.mark.unit
@pytest.mark.parametrize("freshness", [None, RuntimeError("supabase read failed")])
def test_macro_fallback_fires_when_layer_unknown_or_probe_errors(monkeypatch, freshness):
    # Empty table (None) or a probe error both fail-soft to "stale" → paid search
    # fires, so grounding is never silently dropped.
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    _stub_freshness(monkeypatch, freshness)
    monkeypatch.setattr(
        "digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding",
        lambda **_k: {"summary": "fallback", "sources": [], "as_of": "2026-06-13"},
    )
    _tools, _execute, grounding = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=True,
        live_search_is_fallback=True,
        run_date=date(2026, 6, 13),
        model="openrouter/openrouter/auto",
        segment="macro",
    )
    assert grounding is not None


@pytest.mark.unit
def test_ingested_macro_stale_threshold_and_env_override(monkeypatch):
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 6, 7))  # age = 6 days vs run 2026-06-13
    run = date(2026, 6, 13)
    monkeypatch.delenv("ATLAS_MACRO_STALE_DAYS", raising=False)
    assert _node_factory._ingested_macro_stale(run) is False  # 6 <= 7 default
    monkeypatch.setenv("ATLAS_MACRO_STALE_DAYS", "3")
    assert _node_factory._ingested_macro_stale(run) is True  # 6 > 3


@pytest.mark.unit
def test_ingested_macro_stale_normalizes_datetime_freshness(monkeypatch):
    # query_macro_series_freshness can hand back a datetime (datetime subclasses
    # date, so _parse_date returns it unchanged). _ingested_macro_stale must
    # normalize it — `date - datetime` would otherwise raise outside the try and
    # defeat fail-soft. Should compute age cleanly, not crash.
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.delenv("ATLAS_MACRO_STALE_DAYS", raising=False)
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    _stub_freshness(monkeypatch, datetime(2026, 6, 12, 16, 30))  # 1 day before run
    assert _node_factory._ingested_macro_stale(date(2026, 6, 13)) is False


@pytest.mark.unit
def test_ingested_macro_stale_when_data_tools_disabled(monkeypatch):
    # Kill-switch off → can't read the ingested layer → treat as stale (paid path).
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "0")
    assert _node_factory._ingested_macro_stale(date(2026, 6, 13)) is True


@pytest.mark.unit
def test_non_fallback_live_search_ignores_freshness(monkeypatch):
    # A plain live_search segment (live_search_is_fallback=False) must always fire
    # web_search regardless of ingested-layer freshness — the gate is opt-in.
    monkeypatch.setenv("ATLAS_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_atlas_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 6, 13))  # perfectly fresh

    def _probe_should_not_run(_run_date):
        raise AssertionError("freshness probe must not run for non-fallback live_search")

    monkeypatch.setattr(_node_factory, "_ingested_macro_stale", _probe_should_not_run)
    monkeypatch.setattr(
        "digiquant.olympus.atlas.data.web_grounding.fetch_web_grounding",
        lambda **_k: {"summary": "always", "sources": [], "as_of": "2026-06-13"},
    )
    _tools, _execute, grounding = _node_factory.build_grounding(
        use_data_tools=False,
        live_search=True,
        live_search_is_fallback=False,
        run_date=date(2026, 6, 13),
        model="openrouter/openrouter/auto",
        segment="international",
    )
    assert grounding is not None and grounding["summary"] == "always"
