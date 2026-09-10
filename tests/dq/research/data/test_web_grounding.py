from __future__ import annotations

from datetime import date
from typing import Any
from unittest.mock import patch

import pytest

# web_grounding imports digigraph.llm, which requires `openai` (a digigraph dep absent
# in the digiquant-only CI job). Skip cleanly there; runs in research-graph-ci / locally.
pytest.importorskip("openai")

from digiquant.research.data import web_grounding

# Saved before the autouse fixture below replaces the module attr, so the
# bearer-threading tests below exercise the real tool call (#3859 Task 2).
_real_call_web_search_tool = web_grounding.call_web_search_tool


@pytest.fixture(autouse=True)
def _tool_unavailable(monkeypatch: pytest.MonkeyPatch):
    """Legacy-path tests: force the tool-first call to fail so the synthesis fallback runs."""

    def _raise(**kwargs):
        raise RuntimeError("web-search tool unavailable")

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _raise)


def _query_for(segment: str) -> str:
    captured: dict[str, str] = {}

    def _ws(model: str, query: str):
        captured["query"] = query
        return ("- x[[1]](u)", ["https://u"])

    with patch.object(web_grounding, "_openrouter_web_search", side_effect=_ws):
        web_grounding.fetch_web_grounding(
            model="openrouter/perplexity/sonar",
            segment=segment,
            run_date=date(2026, 6, 9),
        )
    return captured["query"]


@pytest.mark.unit
def test_fetch_web_grounding_uses_tool(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.research.data import web_grounding as mod

    monkeypatch.setattr(
        mod,
        "call_web_search_tool",
        lambda **k: {"summary": "s", "sources": ["https://a.com/1"]},
    )
    out = mod.fetch_web_grounding(
        model="cheap", segment="macro", run_date="2026-09-10", scope="test"
    )
    assert out is not None
    assert out["sources"] == ["https://a.com/1"]


@pytest.mark.unit
def test_fetch_web_grounding_returns_summary_and_sources():
    with patch.object(
        web_grounding,
        "_openrouter_web_search",
        return_value=("- CPI rose 0.6%[[1]](u)", ["https://u"]),
    ):
        out = web_grounding.fetch_web_grounding(
            model="openrouter/perplexity/sonar", segment="macro", run_date=date(2026, 6, 9)
        )
    assert out is not None
    assert out["summary"].startswith("- CPI")
    assert out["sources"] == ["https://u"]
    assert out["as_of"] == "2026-06-09"


@pytest.mark.unit
def test_per_segment_domains_folded_into_query_and_capped():
    # Native search has no Exa allowlist — domains are a soft preference in the query (#2567).
    politician = _query_for("alt-politician-signals")
    assert "capitoltrades.com" in politician

    macro = _query_for("macro")
    assert "federalreserve.gov" in macro and "bls.gov" in macro


@pytest.mark.unit
def test_unmapped_segment_falls_back_to_default_allowlist_in_query():
    query = _query_for("some-unmapped-segment")
    assert "reuters.com" in query  # the default web_allowed_websites


@pytest.mark.unit
def test_dashboard_grounding_does_not_pass_exa_params():
    """dashboard must not assemble engine=/max_results= for the digillm Exa toolkit (#2567)."""
    captured: dict = {}

    def _or_ws(model, query, **kwargs):
        captured["kwargs"] = kwargs
        return ("- ok[[1]](https://u)", ["https://u"])

    with patch("digigraph.llm_client.openrouter_web_search", side_effect=_or_ws):
        web_grounding.fetch_web_grounding(
            model="openrouter/perplexity/sonar",
            segment="macro",
            run_date=date(2026, 6, 9),
        )
    assert captured["kwargs"] == {}


@pytest.mark.unit
def test_fetch_web_grounding_none_when_search_unavailable():
    with patch.object(web_grounding, "_openrouter_web_search", return_value=None):
        assert (
            web_grounding.fetch_web_grounding(
                model="ollama/local", segment="macro", run_date=date(2026, 6, 9)
            )
            is None
        )


@pytest.mark.unit
def test_fetch_web_grounding_none_on_empty_text():
    with patch.object(web_grounding, "_openrouter_web_search", return_value=("   ", [])):
        assert (
            web_grounding.fetch_web_grounding(
                model="openrouter/openrouter/auto", segment="macro", run_date=date(2026, 6, 9)
            )
            is None
        )


@pytest.mark.unit
def test_fetch_web_grounding_raises_when_required(monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setenv("OLYMPUS_WEB_SEARCH", "required")
    with patch.object(web_grounding, "_openrouter_web_search", return_value=None):
        with pytest.raises(web_grounding.DashboardWebSearchError):
            web_grounding.fetch_web_grounding(
                model="openrouter/perplexity/sonar", segment="macro", run_date=date(2026, 6, 9)
            )


@pytest.mark.unit
def test_build_grounding_live_search_without_data_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Web grounding must not be gated on DIGIQUANT_RESEARCH_DATA_TOOLS (#946)."""
    from digiquant.research.phases import _node_factory as nf

    monkeypatch.setenv("DIGIQUANT_RESEARCH_DATA_TOOLS", "0")
    grounding = {"summary": "ok", "sources": [], "as_of": "2026-06-09"}
    with patch(
        "digiquant.research.data.web_grounding.fetch_web_grounding",
        return_value=grounding,
    ):
        tools, execute_tool, web_grounding = nf.build_grounding(
            use_data_tools=True,
            live_search=True,
            run_date=date(2026, 6, 9),
            segment="alt-sentiment-news",
        )
    assert tools is None
    assert execute_tool is None
    assert web_grounding == grounding


def _fake_hub_results(seen: dict[str, Any]):
    """Fake `_call_digisearch_web_search` capturing kwargs, returning one row."""

    def fake_call(query: str, **kw: Any) -> dict[str, Any]:
        seen.update(kw)
        return {
            "content": "- [t](https://a.com/1): s",
            "results": [
                {
                    "doc_id": "https://a.com/1",
                    "content": "s",
                    "metadata": {"title": "t"},
                }
            ],
        }

    return fake_call


@pytest.mark.unit
def test_pipeline_bearer_threaded(monkeypatch: pytest.MonkeyPatch) -> None:
    """Pipeline hub calls carry the Task 1 service JWT (#3859 Task 2).

    Adapted from the brief: the real `_call_digisearch_web_search` takes
    `context` (bearer via `context.state["digi_bearer"]`), not `bearer_token`,
    and both seams are lazily imported at call time, so patch the sources.
    """
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", _fake_hub_results(seen))
    out = _real_call_web_search_tool(query="etf flows", include_domains=[], max_results=4)
    assert out["sources"] == ["https://a.com/1"]
    context = seen.get("context")
    assert context is not None
    assert context.state.get("digi_bearer") == "svc-jwt"


@pytest.mark.unit
def test_explicit_bearer_token_wins_over_pipeline(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """An explicit `bearer_token` threads through and skips the JWT exchange."""
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    def _boom(**k: Any) -> str:
        raise AssertionError("get_service_jwt must not run with explicit bearer")

    monkeypatch.setattr(sa_mod, "get_service_jwt", _boom)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", _fake_hub_results(seen))
    out = _real_call_web_search_tool(
        query="etf flows", include_domains=[], max_results=4, bearer_token="explicit"
    )
    assert out["sources"] == ["https://a.com/1"]
    context = seen.get("context")
    assert context is not None
    assert context.state.get("digi_bearer") == "explicit"


@pytest.mark.unit
def test_pipeline_bearer_auth_error_propagates(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """`ServiceAuthError` from the JWT exchange propagates (never swallowed)."""
    import digibase.service_auth as sa_mod
    from digibase.service_auth import ServiceAuthError

    def _raise(**k: Any) -> str:
        raise ServiceAuthError("DIGIQUANT_DIGIKEY_API_KEY is not set")

    monkeypatch.setattr(sa_mod, "get_service_jwt", _raise)
    with pytest.raises(ServiceAuthError):
        _real_call_web_search_tool(query="etf flows", include_domains=[], max_results=4)
