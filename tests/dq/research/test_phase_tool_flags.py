from __future__ import annotations

from datetime import date, datetime
from pathlib import Path

import pytest
import yaml
from digiquant.data.gloomberb import EQUITY_TOOLS, MACRO_TOOLS
from digiquant.research.phases import _node_factory
from digiquant.research.phases.phase1_altdata import _SPECS as ALT_SPECS
from digiquant.research.phases.phase2_institutional import _SPECS as INST_SPECS
from digiquant.research.phases.phase3_macro import _SPEC as MACRO
from digiquant.research.phases.phase4_assetclass import _SPECS as ASSET_SPECS
from digiquant.research.phases.phase5_equities import _EQUITY_SPEC, _sector_spec
from digiquant.research.sectors_config import load_sectors


@pytest.mark.unit
def test_macro_uses_data_tools_and_fallback_search():
    assert MACRO.use_data_tools is True
    assert MACRO.live_search is True
    # #711: macro's web_search is now a stale-only paid fallback, not a daily input.
    assert MACRO.live_search_is_fallback is True


@pytest.mark.unit
def test_alt_phases_grounding_modes():
    # Three alt-data segments do not fire a web_search pre-pass: options reads the
    # Supabase data tools (#708); onchain reads the Hyperdash divergence preflight injects
    # into market_context (#801); politician-signals is contained per Counsel's DIG-1251
    # ruling (DIG-1252) — the feed is refused, so the nightly harvest must not go out to
    # capitoltrades.com / quiverquant.com. Every other alt-data segment grounds on web/x search.
    by_slug = {s.segment_slug: s for s in ALT_SPECS}
    opts = by_slug["alt-options-derivatives"]
    assert opts.use_data_tools is True
    assert opts.live_search is False and opts.ai_portfolios is False
    onchain = by_slug["alt-onchain-positioning"]
    assert onchain.use_data_tools is False  # reads injected market_context, not data tools
    assert onchain.live_search is False and onchain.ai_portfolios is False
    # DIG-1252 containment: the segment stays in the fan-out, its skill and its published
    # history stay in tree, but it must never fire the nightly web_search pre-pass — that
    # pre-pass is what reached capitoltrades.com / quiverquant.com.
    politician = by_slug["alt-politician-signals"]
    assert politician.use_data_tools is False
    assert politician.live_search is False and politician.ai_portfolios is False
    # Every remaining alt-data segment grounds on soft signals (web/x search), never data tools.
    _deterministic = {
        "alt-options-derivatives",
        "alt-onchain-positioning",
        "alt-politician-signals",
    }
    for spec in ALT_SPECS:
        if spec.segment_slug in _deterministic:
            continue
        assert spec.use_data_tools is False, spec.segment_slug
        assert spec.live_search or spec.ai_portfolios, spec.segment_slug
    # alt-ai-portfolios uses the tool-only web_search grounding pre-pass;
    # the rest use live_search grounding.
    assert by_slug["alt-ai-portfolios"].ai_portfolios is True
    assert by_slug["alt-ai-portfolios"].live_search is False
    assert by_slug["alt-sentiment-news"].live_search is True


@pytest.mark.unit
def test_politician_signals_makes_no_paid_search(monkeypatch):
    # DIG-1252 done-test. Counsel ruled this feed permanently refused, so no run of this
    # segment may reach the `web_search` pre-pass in web_grounding.py — that call is the
    # single outbound hop, and search_domains.yaml scopes it to capitoltrades.com /
    # quiverquant.com / sec.gov. Model the options segment's guard: a call here is the bug.
    def _fail(**_k):  # a paid web_search call here would be the bug
        raise AssertionError("alt-politician-signals must not call fetch_web_grounding")

    monkeypatch.setattr("digiquant.research.data.web_grounding.fetch_web_grounding", _fail)
    spec = next(s for s in ALT_SPECS if s.segment_slug == "alt-politician-signals")
    # Same argument shape _node_factory.build_node passes in production, so this fails if
    # any other input ever re-opens the outbound path.
    tools, _execute, grounding = _node_factory.build_grounding(
        use_data_tools=spec.use_data_tools,
        live_search=spec.live_search,
        live_search_is_fallback=spec.live_search_is_fallback,
        run_date=date(2026, 10, 6),
        model="openrouter/openrouter/auto",
        segment=spec.segment_slug,
        ai_portfolios=spec.ai_portfolios,
        use_research_tools=spec.use_research_tools,
        research_phase=spec.research_phase,
        digifetch_tools=spec.digifetch_tools,
    )
    assert grounding is None
    # Whatever tools survive are corpus reads (Supabase/R2 on our own account); none of
    # them may be an outbound web or Gloomberb/digifetch call.
    names = [str((t.get("function") or t).get("name", "")) for t in (tools or [])]
    assert not [n for n in names if "web_search" in n or n.startswith("digifetch_")]


@pytest.mark.unit
def test_inst_phases_use_live_search_only():
    for spec in INST_SPECS:
        assert spec.live_search is True, spec.segment_slug
        assert spec.use_data_tools is False, spec.segment_slug


# --- #4146: digifetch family flags (curated subset per phase) -----------------


@pytest.mark.unit
def test_macro_uses_the_macro_digifetch_subset():
    assert MACRO.digifetch_tools == MACRO_TOOLS


@pytest.mark.unit
def test_equity_and_sector_specs_use_the_equity_digifetch_subset():
    assert _EQUITY_SPEC.digifetch_tools == EQUITY_TOOLS
    sectors = load_sectors()
    assert sectors
    assert _sector_spec(sectors[0]).digifetch_tools == EQUITY_TOOLS


@pytest.mark.unit
def test_other_research_specs_stay_digifetch_free():
    for spec in (*ALT_SPECS, *INST_SPECS, *ASSET_SPECS):
        assert spec.digifetch_tools is None, spec.segment_slug


@pytest.mark.unit
def test_asset_classes_use_data_tools():
    for spec in ASSET_SPECS:
        assert spec.use_data_tools is True, spec.segment_slug
    # International also web-searches for non-US market/M2 freshness.
    intl = next(s for s in ASSET_SPECS if s.segment_slug == "international")
    assert intl.live_search is True


@pytest.mark.unit
def test_build_grounding_respects_kill_switch(monkeypatch):
    monkeypatch.setattr(_node_factory, "_research_data_client", object)
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
        lambda **_k: {"summary": "x", "sources": [], "as_of": "2026-06-08"},
    )
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "0")
    tools, execute_tool, grounding = _node_factory.build_grounding(
        use_data_tools=True,
        live_search=True,
        run_date=date(2026, 6, 8),
        model="openrouter/openrouter/auto",
    )
    # DIGIQUANT_RESEARCH_DATA_TOOLS disables Supabase data tools only; live_search pre-pass is independent.
    assert tools is None and execute_tool is None
    assert grounding is not None

    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
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
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_research_data_client", object)

    def _fail(**_k):  # a paid web_search call here would be the bug
        raise AssertionError("options segment must not call fetch_web_grounding")

    monkeypatch.setattr("digiquant.research.data.web_grounding.fetch_web_grounding", _fail)
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
    # Only VIXCLS + VXVCLS stay on the gloomberb panel (#4794 PR3):
    # VXNCLS/GVZCLS/OVXCLS are not served, so they must not be re-added.
    import yaml
    from digiquant.data.prices.gloomberb_macro import DROPPED_SERIES_IDS
    from digiquant.research.graph import _research_config_root

    raw = yaml.safe_load((_research_config_root() / "macro_series.yaml").read_text())
    ids = {s["id"] for s in raw["fred"]["series"]}
    assert {"VIXCLS", "VXVCLS"} <= ids
    assert ids.isdisjoint(DROPPED_SERIES_IDS)


@pytest.mark.unit
def test_build_grounding_degrades_when_client_unavailable(monkeypatch):
    # A missing/broken Supabase client must not crash the phase: data tools are
    # dropped, but web grounding (which needs no Supabase client) still works.
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
        lambda **_k: {"summary": "x", "sources": [], "as_of": "2026-06-08"},
    )

    def _boom():
        raise RuntimeError("supabase not configured")

    monkeypatch.setattr(_node_factory, "_research_data_client", _boom)
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

    monkeypatch.setattr("digiquant.research.supabase_io.query_macro_series_freshness", _impl)


@pytest.mark.unit
def test_macro_fallback_skips_paid_search_when_layer_fresh(monkeypatch):
    # Fresh ingested FRED layer → the fallback web_search must NOT fire; the
    # segment grounds on data tools alone. This is the Phase D cost cut.
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.delenv("DIGIQUANT_MACRO_STALE_DAYS", raising=False)
    monkeypatch.setattr(_node_factory, "_research_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 6, 12))  # 1 day stale → fresh

    def _fail(**_k):
        raise AssertionError("fresh ingested layer must not fire the paid fallback web_search")

    monkeypatch.setattr("digiquant.research.data.web_grounding.fetch_web_grounding", _fail)
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
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.delenv("DIGIQUANT_MACRO_STALE_DAYS", raising=False)
    monkeypatch.setattr(_node_factory, "_research_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 5, 1))  # >7 days stale
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
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
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_research_data_client", object)
    _stub_freshness(monkeypatch, freshness)
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
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
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_research_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 6, 7))  # age = 6 days vs run 2026-06-13
    run = date(2026, 6, 13)
    monkeypatch.delenv("DIGIQUANT_MACRO_STALE_DAYS", raising=False)
    assert _node_factory._ingested_macro_stale(run) is False  # 6 <= 7 default
    monkeypatch.setenv("DIGIQUANT_MACRO_STALE_DAYS", "3")
    assert _node_factory._ingested_macro_stale(run) is True  # 6 > 3


@pytest.mark.unit
def test_ingested_macro_stale_normalizes_datetime_freshness(monkeypatch):
    # query_macro_series_freshness can hand back a datetime (datetime subclasses
    # date, so _parse_date returns it unchanged). _ingested_macro_stale must
    # normalize it — `date - datetime` would otherwise raise outside the try and
    # defeat fail-soft. Should compute age cleanly, not crash.
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.delenv("DIGIQUANT_MACRO_STALE_DAYS", raising=False)
    monkeypatch.setattr(_node_factory, "_research_data_client", object)
    _stub_freshness(monkeypatch, datetime(2026, 6, 12, 16, 30))  # 1 day before run
    assert _node_factory._ingested_macro_stale(date(2026, 6, 13)) is False


@pytest.mark.unit
def test_ingested_macro_stale_when_data_tools_disabled(monkeypatch):
    # Kill-switch off → can't read the ingested layer → treat as stale (paid path).
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "0")
    assert _node_factory._ingested_macro_stale(date(2026, 6, 13)) is True


@pytest.mark.unit
def test_non_fallback_live_search_ignores_freshness(monkeypatch):
    # A plain live_search segment (live_search_is_fallback=False) must always fire
    # web_search regardless of ingested-layer freshness — the gate is opt-in.
    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "1")
    monkeypatch.setattr(_node_factory, "_research_data_client", object)
    _stub_freshness(monkeypatch, date(2026, 6, 13))  # perfectly fresh

    def _probe_should_not_run(_run_date):
        raise AssertionError("freshness probe must not run for non-fallback live_search")

    monkeypatch.setattr(_node_factory, "_ingested_macro_stale", _probe_should_not_run)
    monkeypatch.setattr(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
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


# --- DIG-1252 publish-side guard (Counsel, DIG-1251 ruling eca4b9a9 edits 1-6) ---
#
# Containment: the alt-politician-signals segment must not source, prompt for, or
# publish STOCK Act trade-level content from a commercial aggregator. 5 U.S.C.
# 13107(c)(1)(B) bars obtaining or using such a "report" for a non-news-media
# commercial purpose; Counsel ruled that collection stops the statutory breach, and
# that what remains is a narrower accuracy / consumer-protection exposure from the
# prompt still asserting trades it can no longer verify.
#
# The refused domains are written as literals here on purpose: this guard must hold
# on any branch, including ones that predate a REFUSED_SEARCH_DOMAINS constant. It
# reads the *prompt* and the *domain list*, not the search call path, because the
# prompt is what survives the flag being turned off.

_REFUSED_POLITICIAN_DOMAINS = ("capitoltrades.com", "quiverquant.com")


def _politician_skill_text() -> str:
    import digiquant.research as _research

    skill = (
        Path(_research.__file__).resolve().parent / "skills" / "alt-politician-signals" / "SKILL.md"
    )
    assert skill.is_file(), f"segment skill file missing: {skill}"
    return skill.read_text(encoding="utf-8")


@pytest.mark.unit
def test_politician_skill_prompts_no_refused_domain():
    text = _politician_skill_text().lower()
    for domain in _REFUSED_POLITICIAN_DOMAINS:
        assert domain not in text, f"SKILL.md still names the refused source {domain}"


@pytest.mark.unit
def test_politician_skill_has_no_trade_disclosure_step():
    # Counsel edit 1: delete the STOCK Act Trade Disclosures step outright -- do not
    # soften it and do not gate it on web_grounding being present.
    #
    # Assert on the removed *step*, not on the phrase: the scope-limit paragraph still
    # names STOCK Act in order to forbid it, and forbidding the word would forbid the
    # prohibition.
    text = _politician_skill_text().lower()
    assert "stock act trade disclosures" not in text, "SKILL.md still carries the trade step"
    assert "congressional trades disclosed" not in text, "SKILL.md still instructs the trade search"
    for trade_term in ("quiver quantitative", "capitol trades"):
        assert trade_term not in text, f"SKILL.md still instructs searching {trade_term}"


@pytest.mark.unit
def test_politician_skill_output_skeleton_has_no_trades_section():
    # Counsel edit 4: the "## Congressional trades" block is gone from the skeleton.
    assert "## congressional trades" not in _politician_skill_text().lower()


@pytest.mark.unit
def test_politician_segment_domain_list_names_no_refused_domain():
    """Activate once DIG-1133's deny layer lands; assert nothing until then.

    search_domains.yaml still lists the refused domains on branches that predate
    DIG-1133, and Counsel assigned that edit to that branch so the two do not
    conflict. Importing the constant means this assertion switches itself on the
    moment the deny layer exists, with no edit here.
    """
    try:
        from digiquant.research.data.web_grounding import REFUSED_SEARCH_DOMAINS
    except ImportError:
        pytest.skip("no REFUSED_SEARCH_DOMAINS yet; DIG-1133 deny layer not merged")

    from digiquant.research.graph import _research_config_root

    config = yaml.safe_load(
        (_research_config_root() / "search_domains.yaml").read_text(encoding="utf-8")
    )
    domains = config.get("per_segment", {}).get("alt-politician-signals", []) or []
    for domain in domains:
        assert domain not in REFUSED_SEARCH_DOMAINS, f"domain list still carries refused {domain}"


def test_politician_skill_steps_have_no_trade_step():
    """Guard the step headings, not just the exact wording we removed (review SF3).

    A re-introduction titled e.g. "### 1. Congressional Trading Activity" passes all three
    wording guards above, so assert on the headings themselves.
    """
    import re as _re

    text = _politician_skill_text()
    headings = _re.findall(r"^###\s*\d+\.\s*(.+)$", text, flags=_re.MULTILINE)
    assert headings, "no numbered steps found; the prompt structure changed shape"
    for heading in headings:
        # "Tariff & Trade Actions" is lawful policy work, so trade/tariff is allowed only
        # when the heading says trade-POLICY. Filing/disclosure/congressional is never allowed.
        assert not _re.search(r"filing|disclosure|congress", heading, _re.IGNORECASE), (
            f"step heading reintroduces trade-level content: {heading!r}"
        )
        if _re.search(r"\btrade\b", heading, _re.IGNORECASE):
            assert _re.search(r"tariff|policy", heading, _re.IGNORECASE), (
                f"step heading names trades without saying policy/tariff: {heading!r}"
            )
