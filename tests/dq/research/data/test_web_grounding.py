"""Tool-only web grounding: requested search succeeds or raises (#3859 Task 4).

No synthesis fallback, no required-gate: ``fetch_web_grounding`` returns
``{"summary", "sources", "as_of"}`` or raises ``DashboardWebSearchError``
unconditionally. Skipped-by-design paths (fresh ingested layer,
``live_search=False``) never call the tool and never raise.
"""

from __future__ import annotations

from datetime import date
from typing import Any

import pytest

pytest.importorskip("openai")

from digiquant.research.data import web_grounding

# Saved so the bearer-threading tests below exercise the real tool call (#3859 Task 2).
_real_call_web_search_tool = web_grounding.call_web_search_tool


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
def test_fetch_web_grounding_returns_summary_sources_as_of(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_grounding,
        "call_web_search_tool",
        lambda **k: {"summary": "- CPI rose 0.6%", "sources": ["https://u"]},
    )
    out = web_grounding.fetch_web_grounding(
        model="cheap", segment="macro", run_date=date(2026, 6, 9)
    )
    assert out["summary"].startswith("- CPI")
    assert out["sources"] == ["https://u"]
    assert out["as_of"] == "2026-06-09"


@pytest.mark.unit
def test_fetch_web_grounding_raises_on_empty(monkeypatch: pytest.MonkeyPatch) -> None:
    from digiquant.research.data import web_grounding as mod

    monkeypatch.setattr(
        mod, "call_web_search_tool", lambda **k: (_ for _ in ()).throw(RuntimeError("no rows"))
    )
    with pytest.raises(mod.DashboardWebSearchError):
        mod.fetch_web_grounding(model="cheap", segment="macro", run_date="2026-09-11", scope="test")


@pytest.mark.unit
def test_fetch_web_grounding_raises_on_tool_error(monkeypatch: pytest.MonkeyPatch) -> None:
    def _boom(**kwargs: Any) -> dict[str, Any]:
        raise RuntimeError("hub 503")

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _boom)
    with pytest.raises(web_grounding.DashboardWebSearchError) as excinfo:
        web_grounding.fetch_web_grounding(model="cheap", segment="macro", run_date=date(2026, 6, 9))
    assert isinstance(excinfo.value.__cause__, RuntimeError)


@pytest.mark.unit
def test_fetch_web_grounding_raises_on_blank_summary(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    monkeypatch.setattr(
        web_grounding,
        "call_web_search_tool",
        lambda **k: {"summary": "   ", "sources": []},
    )
    with pytest.raises(web_grounding.DashboardWebSearchError):
        web_grounding.fetch_web_grounding(model="cheap", segment="macro", run_date=date(2026, 6, 9))


@pytest.mark.unit
def test_fetch_web_grounding_passes_domains_through(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """No domain folding into the query: yaml lists go to the tool as params (#3859)."""
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"summary": "s", "sources": ["https://u"]}

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _fake)
    web_grounding.fetch_web_grounding(model="cheap", segment="macro", run_date=date(2026, 6, 9))
    assert seen["include_domains"] == [
        "federalreserve.gov",
        "bls.gov",
        "treasury.gov",
        "reuters.com",
        "apnews.com",
    ]
    assert seen["exclude_domains"] == []
    assert seen["max_results"] == 4
    assert "federalreserve.gov" not in seen["query"]
    assert "Prefer sources among" not in seen["query"]


@pytest.mark.unit
def test_fetch_web_grounding_domain_overrides(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"summary": "s", "sources": ["https://u"]}

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _fake)
    web_grounding.fetch_web_grounding(
        model="cheap",
        segment="macro",
        run_date=date(2026, 6, 9),
        include_domains=["example.com"],
        exclude_domains=["bad.com"],
        max_results=7,
    )
    assert seen["include_domains"] == ["example.com"]
    assert seen["exclude_domains"] == ["bad.com"]
    assert seen["max_results"] == 7


@pytest.mark.unit
def test_unmapped_segment_uses_default_allowlist(monkeypatch: pytest.MonkeyPatch) -> None:
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"summary": "s", "sources": ["https://u"]}

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _fake)
    web_grounding.fetch_web_grounding(
        model="cheap", segment="some-unmapped-segment", run_date=date(2026, 6, 9)
    )
    assert "reuters.com" in seen["include_domains"]  # the default web_allowed_websites


@pytest.mark.unit
def test_segment_node_raises_when_requested_grounding_absent() -> None:
    """A live_search segment with no grounding aborts loud — no flag, no silent run."""
    from unittest.mock import patch

    from digiquant.research.phases._node_factory import SegmentNodeSpec, build_segment_node
    from digiquant.research.segments import SegmentReport
    from digiquant.research.state import ResearchState

    spec = SegmentNodeSpec(
        segment_slug="test-live",
        skill_slug="alt-sentiment-news",
        output_model=SegmentReport,
        phase_outputs_field="phase1_outputs",
        live_search=True,
    )
    node = build_segment_node(spec)
    state = ResearchState(run_type="baseline", run_date=date(2026, 6, 20))
    with (
        patch(
            "digiquant.research.phases._node_factory.build_grounding",
            return_value=(None, None, None),
        ),
        patch(
            "digiquant.research.phases._node_factory.run_research_agent",
            side_effect=AssertionError("ungrounded LLM call must not run"),
        ),
    ):
        with pytest.raises(web_grounding.DashboardWebSearchError):
            node(state)


@pytest.mark.unit
def test_segment_node_skips_quietly_when_not_requested() -> None:
    """Skipped-by-design segments (fallback skip, live_search=False) never raise."""
    from unittest.mock import patch

    from digiquant.research.phases._node_factory import SegmentNodeSpec, build_segment_node
    from digiquant.research.segments import SegmentReport
    from digiquant.research.state import ResearchState

    specs = [
        SegmentNodeSpec(
            segment_slug="test-fallback",
            skill_slug="macro",
            output_model=SegmentReport,
            phase_outputs_field="phase1_outputs",
            live_search=True,
            live_search_is_fallback=True,
            use_data_tools=True,
        ),
        SegmentNodeSpec(
            segment_slug="test-no-search",
            skill_slug="alt-options-derivatives",
            output_model=SegmentReport,
            phase_outputs_field="phase1_outputs",
            live_search=False,
        ),
    ]
    for spec in specs:
        captured: dict[str, Any] = {}

        def _fake_research_agent(
            skill_text: str,
            phase_inputs: dict,
            shared_context: dict,
            output_model: type,
            **kwargs: Any,
        ) -> Any:
            captured.update(phase_inputs)
            return output_model.model_validate(
                {
                    "segment": spec.segment_slug,
                    "date": "2026-06-20",
                    "bias": "neutral",
                    "headline": "test",
                    "material_findings": [],
                    "sources": [],
                    "notes": "",
                }
            )

        node = build_segment_node(spec)
        with (
            patch(
                "digiquant.research.phases._node_factory.build_grounding",
                return_value=(None, None, None),
            ),
            patch(
                "digiquant.research.phases._node_factory.run_research_agent",
                side_effect=_fake_research_agent,
            ),
        ):
            node(ResearchState(run_type="baseline", run_date=date(2026, 6, 20)))
        assert "web_grounding" not in captured
        assert "grounding_absent" not in captured


@pytest.mark.unit
def test_build_grounding_live_search_without_data_tools(monkeypatch: pytest.MonkeyPatch) -> None:
    """Web grounding must not be gated on DIGIQUANT_RESEARCH_DATA_TOOLS (#946)."""
    from unittest.mock import patch

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

    def _raise(**k: Any) -> str:
        raise sa_mod.ServiceAuthError("DIGIQUANT_DIGIKEY_API_KEY is not set")

    monkeypatch.setattr(sa_mod, "get_service_jwt", _raise)
    with pytest.raises(sa_mod.ServiceAuthError):
        _real_call_web_search_tool(query="etf flows", include_domains=[], max_results=4)
