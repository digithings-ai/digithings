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
def test_exclude_domains_is_capped_at_the_request_limit(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """digisearch caps ``exclude_domains`` at 20 and rejects the whole request
    over it — the same class as the query cap (#4163). Drop the extras loudly
    rather than shipping a rejection that fails the segment."""
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"summary": "s", "sources": ["https://u"]}

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _fake)
    with caplog.at_level("WARNING", logger="digiquant.research.data.web_grounding"):
        web_grounding.fetch_web_grounding(
            model="cheap",
            segment="macro",
            run_date=date(2026, 6, 9),
            exclude_domains=[f"d{i}.example" for i in range(25)],
        )
    assert seen["exclude_domains"] == [f"d{i}.example" for i in range(20)]
    assert "exclude_domains" in caplog.text


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


@pytest.mark.unit
def test_hub_failure_reaches_the_segment_error_unmasked(monkeypatch: pytest.MonkeyPatch) -> None:
    """A digisearch hub failure is surfaced with its own text (#4106).

    Regression for 2026-09-15: a hosted-digisearch 429 was collapsed into
    "web_search returned no rows", which hid the cause for a day of book-run
    debugging. The bundled ``DigisearchHubError`` must reach
    ``DashboardWebSearchError`` intact.
    """
    from digigraph.orchestration import web_search_tools
    from digiquant.research.data import web_grounding as mod

    def _boom(*_a: Any, **_k: Any) -> dict[str, Any]:
        raise web_search_tools.DigisearchHubError(
            "digisearch web_search failed: Client error '429 Too Many Requests'"
        )

    monkeypatch.setattr(mod, "call_web_search_tool", _boom)
    with pytest.raises(mod.DashboardWebSearchError) as excinfo:
        mod.fetch_web_grounding(segment="beliefs-distillation", run_date="2026-09-15")
    message = str(excinfo.value)
    assert "429" in message
    assert "beliefs-distillation" in message
    assert "returned no rows" not in message


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
def test_an_oversize_query_is_truncated_not_sent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """digisearch rejects a >500-char query, which used to fail a whole book run
    (#4163). Clamp at the boundary and warn instead of shipping the rejection."""
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")
    seen: dict[str, Any] = {}

    def fake_call(query: str, **kw: Any) -> dict[str, Any]:
        seen["query"] = query
        return {
            "content": "- [t](https://a.com/1): s",
            "results": [{"doc_id": "https://a.com/1", "content": "s", "metadata": {"title": "t"}}],
        }

    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", fake_call)
    with caplog.at_level("WARNING", logger="digiquant.research.data.web_grounding"):
        out = _real_call_web_search_tool(
            query=" ".join(["overlong-query"] * 80), include_domains=[], max_results=4
        )
    assert out["sources"] == ["https://a.com/1"]
    assert len(seen["query"]) <= 500  # digisearch's WebSearchRequest cap (#3853)
    assert seen["query"]  # not truncated to nothing
    assert "truncating" in caplog.text
    # The boundary constant must not drift from the cap being pinned here.
    assert web_grounding._MAX_QUERY_CHARS == 500


@pytest.mark.unit
def test_the_query_is_a_search_query_not_a_synthesis_prompt(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """digisearch's ``web_search`` returns result rows and ``call_web_search_tool``
    formats the summary, so instruction text only dilutes retrieval and eats the
    500-char cap (#4165; same shape as ``ai_portfolios._build_query``, #4163)."""
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"summary": "s", "sources": ["https://u"]}

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _fake)
    web_grounding.fetch_web_grounding(model="cheap", segment="macro", run_date=date(2026, 6, 9))
    query = seen["query"]
    assert "macro" in query
    assert "sentiment" in query and "flows" in query
    assert "Summarize" not in query
    assert "search the web" not in query
    assert "bullet points" not in query
    assert len(query) <= web_grounding._MAX_QUERY_CHARS


@pytest.mark.unit
def test_the_query_folds_scope_in_as_keywords(monkeypatch: pytest.MonkeyPatch) -> None:
    """A caller-supplied scope is search context, not a ``Focus on:`` instruction (#4165)."""
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"summary": "s", "sources": ["https://u"]}

    monkeypatch.setattr(web_grounding, "call_web_search_tool", _fake)
    web_grounding.fetch_web_grounding(
        model="cheap", segment="macro", run_date=date(2026, 6, 9), scope="oil inventories"
    )
    assert "oil inventories" in seen["query"]
    assert "Focus on:" not in seen["query"]


@pytest.mark.unit
def test_fetch_web_grounding_passes_config_recency_days(monkeypatch: pytest.MonkeyPatch) -> None:
    """``search_domains.yaml``'s ``recency_days`` must reach the request, not sit
    dead in the file while digisearch's own default applies (#4165)."""
    seen: dict[str, Any] = {}

    def _fake(**kwargs: Any) -> dict[str, Any]:
        seen.update(kwargs)
        return {"summary": "s", "sources": ["https://u"]}

    monkeypatch.setattr(
        web_grounding,
        "_config",
        lambda: {"web_allowed_websites": ["reuters.com"], "recency_days": 30},
    )
    monkeypatch.setattr(web_grounding, "call_web_search_tool", _fake)
    web_grounding.fetch_web_grounding(model="cheap", segment="macro", run_date=date(2026, 6, 9))
    assert seen["recency_days"] == 30


@pytest.mark.unit
def test_recency_days_reaches_the_hub_call(monkeypatch: pytest.MonkeyPatch) -> None:
    """The plumbing seam: ``call_web_search_tool`` -> ``call_digisearch_web_search`` (#4165)."""
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", _fake_hub_results(seen))
    _real_call_web_search_tool(
        query="etf flows", include_domains=[], max_results=4, recency_days=30
    )
    assert seen["recency_days"] == 30


@pytest.mark.unit
def test_recency_days_is_none_when_the_caller_does_not_set_it(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """Unset must stay unset: digisearch applies its own default window (#4165)."""
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", _fake_hub_results(seen))
    _real_call_web_search_tool(query="etf flows", include_domains=[], max_results=4)
    assert seen["recency_days"] is None


@pytest.mark.unit
def test_out_of_range_recency_days_is_clamped_not_sent(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """digisearch accepts ``recency_days`` 1-365 and rejects the whole request
    outside it — the same fail-the-book class as the query/domain caps (#4165)."""
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")
    seen: dict[str, Any] = {}
    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", _fake_hub_results(seen))
    for raw, expected in ((900, 365), (0, 1)):
        seen.clear()
        with caplog.at_level("WARNING", logger="digiquant.research.data.web_grounding"):
            _real_call_web_search_tool(
                query="etf flows", include_domains=[], max_results=4, recency_days=raw
            )
        assert seen["recency_days"] == expected
        assert "recency_days" in caplog.text


def _digisearch_bound(field_name: str, attr: str) -> Any:
    """Read a bound straight from digisearch's request model (drift alarm only)."""
    from digisearch.web_search.models import WebSearchRequest

    for meta in WebSearchRequest.model_fields[field_name].metadata:
        value = getattr(meta, attr, None)
        if value is not None:
            return value
    raise AssertionError(f"WebSearchRequest.{field_name} has no {attr} constraint")


@pytest.mark.unit
def test_local_request_bounds_match_the_digisearch_model() -> None:
    """Drift alarm for the mirrored request bounds (#4165).

    digiquant never imports digisearch at runtime — the tool call goes over the
    hub — so its request bounds are deliberately mirrored constants. Reading
    them back off the model here is what makes lowering digisearch's cap fail
    this suite instead of only failing a live book run.
    """
    assert web_grounding._MAX_QUERY_CHARS == _digisearch_bound("query", "max_length")
    assert web_grounding._MAX_ALLOWED_DOMAINS == _digisearch_bound("include_domains", "max_length")
    assert web_grounding._MAX_EXCLUDED_DOMAINS == _digisearch_bound("exclude_domains", "max_length")
    assert web_grounding._MIN_RECENCY_DAYS == _digisearch_bound("recency_days", "ge")
    assert web_grounding._MAX_RECENCY_DAYS == _digisearch_bound("recency_days", "le")


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


@pytest.mark.unit
def test_scoped_empty_retries_unscoped(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
) -> None:
    """A zero-row scoped search retries without the allowlist (#4086).

    The hosted ddgs provider post-filters by domain (it cannot bias), so a
    narrow allowlist can empty the result set; the retry keeps real grounding
    flowing instead of aborting the pipeline. It is routine, so it is logged
    at debug level rather than as a warning.
    """
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")
    calls: list[dict[str, Any]] = []

    def fake_call(query: str, **kw: Any) -> dict[str, Any]:
        calls.append({"query": query, **kw})
        if kw.get("include_domains"):
            return {"results": []}
        return {
            "results": [
                {
                    "doc_id": "https://b.com/1",
                    "content": "s",
                    "metadata": {"title": "t"},
                }
            ]
        }

    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", fake_call)
    with caplog.at_level("WARNING", logger="digiquant.research.data.web_grounding"):
        out = _real_call_web_search_tool(
            query="etf flows",
            include_domains=["reuters.com"],
            exclude_domains=["spam.example"],
            max_results=4,
        )
    assert "retrying unscoped" not in caplog.text
    assert out["sources"] == ["https://b.com/1"]
    assert out["relaxed_domains"] is True
    assert len(calls) == 2
    assert calls[0]["include_domains"] == ["reuters.com"]
    assert calls[1]["include_domains"] == []
    assert calls[1]["exclude_domains"] == ["spam.example"]
    assert calls[1]["max_results"] == 4


@pytest.mark.unit
def test_fetch_web_grounding_propagates_relaxed_domains(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """The relaxed-allowlist signal reaches callers; absent when not relaxed."""
    from digiquant.research.data import web_grounding as mod

    monkeypatch.setattr(
        mod,
        "call_web_search_tool",
        lambda **k: {"summary": "s", "sources": ["https://a.com/1"], "relaxed_domains": True},
    )
    relaxed = mod.fetch_web_grounding(segment="macro", run_date="2026-09-15")
    assert relaxed["relaxed_domains"] is True

    monkeypatch.setattr(
        mod,
        "call_web_search_tool",
        lambda **k: {"summary": "s", "sources": ["https://a.com/1"]},
    )
    plain = mod.fetch_web_grounding(segment="macro", run_date="2026-09-15")
    assert "relaxed_domains" not in plain


@pytest.mark.unit
def test_unscoped_empty_does_not_retry(monkeypatch: pytest.MonkeyPatch) -> None:
    """With no allowlist there is nothing to relax: one call, then raise."""
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")
    calls: list[dict[str, Any]] = []

    def fake_call(query: str, **kw: Any) -> dict[str, Any]:
        calls.append({"query": query, **kw})
        return {"results": []}

    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", fake_call)
    with pytest.raises(RuntimeError, match="no rows"):
        _real_call_web_search_tool(query="etf flows", include_domains=[], max_results=4)
    assert len(calls) == 1


@pytest.mark.unit
def test_scoped_and_unscoped_empty_raises_with_context(
    monkeypatch: pytest.MonkeyPatch,
) -> None:
    """When even the unscoped retry is empty the error names the scoped domains."""
    import digibase.service_auth as sa_mod
    import digigraph.orchestration.web_search_tools as ws_mod

    monkeypatch.setattr(sa_mod, "get_service_jwt", lambda **k: "svc-jwt")

    def fake_call(query: str, **kw: Any) -> dict[str, Any]:
        return {"results": []}

    monkeypatch.setattr(ws_mod, "_call_digisearch_web_search", fake_call)
    with pytest.raises(RuntimeError, match=r"scoped_domains.*also returned no rows"):
        _real_call_web_search_tool(
            query="etf flows", include_domains=["reuters.com"], max_results=4
        )
