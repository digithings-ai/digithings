"""Research-turn web branch wiring tests (#4064, Task 5).

Graph routing, fail-hard pins, R9 precedence, R10 state/output threading,
node assembly (hit normalization, citation mapping, accounting rebuild),
HTTP/MCP passthrough, and the manifest / package-root surfaces. Every external
boundary is mocked: the Task 3 seams (``_live`` / ``_fetch`` / ``_rank``), the
synthesis monoliths, and the graph nodes themselves. No network, no model
weights, no digillm.
"""

from __future__ import annotations

import ast
import inspect
from typing import Any

import pytest
from digisearch.agent.pipeline_models import ResearchTurnState
from digisearch.core.models import Chunk
from digisearch.search import add_chunks
from digisearch.server import app
from digisearch.web.grounding_models import EFFORT_PRESETS, EffortMode, TurnUsage, WebResearchError
from digisearch.web.retrieve import FetchedPage
from digisearch.web_exa import WebSearchData
from digisearch.web_search.models import WebSearchResult
from fastapi.testclient import TestClient

from tests.digi_test_jwt import auth_headers

pytestmark = pytest.mark.unit


@pytest.fixture
def client() -> TestClient:
    return TestClient(app, headers=auth_headers())


def _hit(url: str, title: str = "", score: float = 0.9, engine: str = "searxng") -> WebSearchResult:
    return WebSearchResult(url=url, title=title, snippet=f"snip {url}", score=score, engine=engine)


def _page(url: str, title: str = "", markdown: str = "") -> FetchedPage:
    return FetchedPage(url=url, title=title, markdown=markdown or f"page body for {url}")


def _retrieval_usage(**overrides: Any) -> dict[str, Any]:
    usage: dict[str, Any] = {
        "searches": 1,
        "pages_fetched": 5,
        "pages_cited": 2,
        "llm_calls": 0,
        "search_ms": 10,
        "fetch_ms": 20,
        "rerank_ms": 30,
        "synthesis_ms": 0,
        "total_ms": 60,
    }
    usage.update(overrides)
    return usage


WEB_HITS = [
    {
        "url": "https://a.com/1",
        "title": "A",
        "snippet": "s a",
        "score": 1.0,
        "engine": "searxng",
    },
    {
        "url": "https://b.com/2",
        "title": "B",
        "snippet": "s b",
        "score": 0.5,
        "engine": "ddgs",
    },
]


def test_web_branch_routes_and_labels_external(monkeypatch):
    from digisearch.agent import web_branch as mod

    pages = [
        {"url": "https://a.com/1", "title": "A", "snippet": "s", "score": 1.0, "engine": "searxng"}
    ]
    monkeypatch.setattr(mod, "node_web_retrieve", lambda s: {"web_hits": pages})
    monkeypatch.setattr(
        mod,
        "node_web_aggregate",
        lambda s: {
            "results": [{**pages[0], "metadata": {"evidence_tier": "External"}}],
            "formatted_context": "[1] https://a.com/1 — A",
            "web_output": {"text": "answer [1]"},
            "cost_dollars": {
                "total": 0.0,
                "provider": "web-oss",
                "breakdown": {"searches": 1, "pages_fetched": 1, "llm_calls": 1},
                "note": "oss-synthesis; llm spend metered in digillm telemetry, not here",
            },
            "usage": {"searches": 1},
        },
    )
    state = ResearchTurnState(user_message="q", source="web", effort="fast")
    out = mod.run_web_research_turn(state.model_dump())
    assert out["backend"] == "web-oss"
    assert out["results"][0]["metadata"]["evidence_tier"] == "External"
    assert out["cost_dollars"]["provider"] == "web-oss"
    assert "llm_calls" in out["cost_dollars"]["breakdown"]


def test_web_branch_fail_hard_pin(monkeypatch):
    from digisearch.agent import web_branch as mod

    def boom(state):
        raise WebResearchError("searxng down")

    monkeypatch.setattr(mod, "node_web_retrieve", boom)
    out = mod.run_web_research_turn({"user_message": "q", "source": "web"})
    assert out["error"] is not None and "searxng down" in out["error"]


def test_source_defaults_to_corpus_and_routes():
    from digisearch.agent.pipeline import _route_after_plan
    from digisearch.agent.pipeline_models import ResearchTurnState

    assert _route_after_plan(ResearchTurnState(user_message="q")) == "retrieve"
    assert _route_after_plan(ResearchTurnState(user_message="q", source="web")) == "web_retrieve"
    assert _route_after_plan(ResearchTurnState(user_message="q", source="auto")) == "web_retrieve"


def test_cited_top_n_request_wins_over_preset():
    from digisearch.agent.web_branch import resolve_web_config
    from digisearch.web.grounding_models import EFFORT_PRESETS, EffortMode

    assert resolve_web_config(effort="fast", cited_top_n=3).cited_top_n == 3
    assert (
        resolve_web_config(effort="fast", cited_top_n=None).cited_top_n
        == EFFORT_PRESETS[EffortMode.FAST].cited_top_n
    )


def test_state_and_output_thread_web_keys():
    from digisearch.agent.pipeline import _output_from_state, _state_from_initial

    state = _state_from_initial(
        {"user_message": "q", "source": "web", "effort": "thorough", "cited_top_n": 3}
    )
    assert state.source == "web" and state.cited_top_n == 3
    out = _output_from_state(
        state.model_copy(
            update={
                "backend": "web-oss",
                "web_output": {"text": "answer [1]"},
                "cost_dollars": {"total": 0.0, "provider": "web-oss"},
                "usage": {"searches": 1},
            }
        )
    )
    dumped = out.model_dump(mode="json")
    assert dumped["backend"] == "web-oss"
    assert dumped["web_output"] == {"text": "answer [1]"}
    assert dumped["cost_dollars"]["provider"] == "web-oss"
    assert dumped["usage"] == {"searches": 1}


def test_web_pages_state_round_trips_as_fetched_pages():
    pages = [
        _page("https://a.com/1", "A", "body a"),
        _page("https://b.com/2", "B", "body b"),
    ]
    state = ResearchTurnState(
        user_message="q",
        source="web",
        web_pages=[page.model_dump(mode="json") for page in pages],
    )

    assert [FetchedPage.model_validate(page) for page in state.web_pages] == pages
    dumped_pages = state.model_dump(mode="json")["web_pages"]
    assert dumped_pages == [page.model_dump(mode="json") for page in pages]
    assert ResearchTurnState(user_message="q").web_pages == []


def test_web_retrieve_normalizes_cited_hits_and_usage(monkeypatch):
    from digisearch.agent import web_branch as mod

    hits = [
        _hit("https://a.com/1", "A", score=0.9, engine="searxng"),
        _hit("https://b.com/2", "B", score=0.4, engine="ddgs"),
    ]
    pages = [
        _page("https://a.com/1", "A", "body a"),
        _page("https://b.com/2", "B", "body b"),
    ]
    seen: dict[str, Any] = {}
    monkeypatch.setattr(
        mod, "_live", lambda q, top_n: (seen.__setitem__("live_top_n", top_n), hits)[1]
    )
    monkeypatch.setattr(
        mod, "_fetch", lambda h, top_n: (seen.__setitem__("fetch_top_n", top_n), pages)[1]
    )

    def fake_rank(question, ranked_pages, top_n):
        seen["rank_top_n"] = top_n
        return [ranked_pages[1]]

    monkeypatch.setattr(mod, "_rank", fake_rank)
    state = ResearchTurnState(user_message="q", source="web", effort="thorough", cited_top_n=2)
    out = mod.node_web_retrieve(state)

    assert out["web_hits"] == [
        {
            "url": "https://b.com/2",
            "title": "B",
            "snippet": "body b",
            "score": 0.4,
            "engine": "ddgs",
        }
    ]
    assert out["web_pages"] == [{"url": "https://b.com/2", "title": "B", "markdown": "body b"}]
    assert seen["live_top_n"] == EFFORT_PRESETS[EffortMode.THOROUGH].live_top_n
    assert seen["fetch_top_n"] == EFFORT_PRESETS[EffortMode.THOROUGH].fetch_top_n
    assert seen["rank_top_n"] == 2
    usage = out["usage"]
    assert usage["searches"] == 1
    assert usage["pages_fetched"] == 2
    assert usage["pages_cited"] == 1
    assert usage["llm_calls"] == 0
    assert usage["total_ms"] == usage["search_ms"] + usage["fetch_ms"] + usage["rerank_ms"]
    step = out["trace"][0]
    assert step.step == "web_retrieve" and step.status == "ok" and step.total == 1
    assert "https://b.com/2" in (step.detail or "")
    assert "body b" not in (step.detail or "")


def test_web_retrieve_invalid_effort_fails_hard():
    from digisearch.agent import web_branch as mod

    out = mod.run_web_research_turn({"user_message": "q", "source": "web", "effort": "slow"})
    assert out["error"] is not None and "invalid effort" in out["error"]
    assert out["backend"] is None
    failed = [step for step in out["trace"] if step["step"] == "web_retrieve"]
    assert failed and failed[0]["status"] == "failed"


def test_web_retrieve_zero_cited_fails_hard(monkeypatch):
    from digisearch.agent import web_branch as mod

    monkeypatch.setattr(mod, "_live", lambda q, top_n: [_hit("https://a.com/1", "A")])
    monkeypatch.setattr(mod, "_fetch", lambda h, top_n: [_page("https://a.com/1", "A")])
    monkeypatch.setattr(mod, "_rank", lambda q, pages, top_n: [])
    out = mod.run_web_research_turn({"user_message": "q", "source": "web"})
    assert out["error"] is not None and "no citable sources" in out["error"]
    assert out["web_output"] is None
    assert out["rag_sources"] == []


def test_web_aggregate_rebuilds_results_citations_and_usage(monkeypatch):
    from digisearch.agent import web_branch as mod

    collapsed = WebSearchData(
        results=[
            {
                "title": "A",
                "url": "https://a.com/1",
                "snippet": "s a",
                "score": 0.0,
                "engine": "",
            }
        ],
        output={"text": "answer [1]"},
        search_type="web-fast",
        cost_dollars={
            "total": 0.0,
            "provider": "web-oss",
            "breakdown": {"searches": 1, "pages_fetched": 1, "llm_calls": 1},
        },
    )
    synthesis = TurnUsage(
        searches=1,
        pages_fetched=1,
        pages_cited=1,
        llm_calls=1,
        rerank_ms=999,
        synthesis_ms=40,
        total_ms=1039,
    )
    seen: dict[str, Any] = {}

    def fake_grounded_answer(question, *, config=None, pages=None):
        seen["question"] = question
        seen["config"] = config
        seen["pages"] = pages
        return collapsed, synthesis

    monkeypatch.setattr(mod, "grounded_answer", fake_grounded_answer)
    state = ResearchTurnState(
        user_message="q",
        source="web",
        effort="fast",
        cited_top_n=2,
        web_hits=WEB_HITS,
        web_pages=[
            _page("https://a.com/1", "A", "s a").model_dump(mode="json"),
            _page("https://b.com/2", "B", "s b").model_dump(mode="json"),
        ],
        usage=_retrieval_usage(),
    )
    out = mod.node_web_aggregate(state)

    assert seen["question"] == "q"
    assert seen["config"].cited_top_n == 2
    assert seen["pages"] == [
        _page("https://a.com/1", "A", "s a"),
        _page("https://b.com/2", "B", "s b"),
    ]
    assert out["backend"] == "web-oss"
    assert out["web_output"] == {"text": "answer [1]"}
    assert out["results"] == [
        {**WEB_HITS[0], "metadata": {"evidence_tier": "External"}},
        {**WEB_HITS[1], "metadata": {"evidence_tier": "External"}},
    ]
    assert out["formatted_context"] == (
        "[1] https://a.com/1 — A — s a\n[2] https://b.com/2 — B — s b"
    )
    first = out["rag_sources"][0]
    assert first["doc_id"] == "https://a.com/1"
    assert first["source_id"] == "https://a.com/1#1"
    assert first["snippet"] == "s a"
    assert first["metadata"]["evidence_tier"] == "External"
    assert first["metadata"]["source_url"] == "https://a.com/1"
    assert first["metadata"]["title"] == "A"
    assert first["metadata"]["engine"] == "searxng"
    assert out["cost_dollars"] == {
        "total": 0.0,
        "provider": "web-oss",
        "breakdown": {"searches": 1, "pages_fetched": 5, "llm_calls": 1},
        "note": "oss-synthesis; llm spend metered in digillm telemetry, not here",
    }
    usage = out["usage"]
    assert usage["pages_fetched"] == 5
    assert usage["pages_cited"] == 2
    assert usage["rerank_ms"] == 30
    assert usage["synthesis_ms"] == 40
    assert usage["llm_calls"] == 1
    assert usage["total_ms"] == 100
    step = out["trace"][0]
    assert step.step == "web_aggregate" and step.status == "ok" and step.total == 2


def test_web_aggregate_structured_path_uses_output_schema(monkeypatch):
    from digisearch.agent import web_branch as mod

    output_schema = {"type": "object", "required": ["answer"]}
    data = WebSearchData(
        results=[
            {
                "title": "A",
                "url": "https://a.com/1",
                "snippet": "s a",
                "score": 0.0,
                "engine": "",
            }
        ],
        output={
            "content": {"answer": "42"},
            "grounding": [
                {
                    "field": "answer",
                    "citations": [{"url": "https://a.com/1"}],
                    "confidence": "high",
                }
            ],
            "text": "{}",
        },
        search_type="web-fast",
    )
    synthesis = TurnUsage(llm_calls=1, synthesis_ms=7, total_ms=507)
    seen: dict[str, Any] = {}

    def fake_structured(question, *, output_schema=None, config=None, pages=None):
        seen["output_schema"] = output_schema
        seen["config"] = config
        seen["pages"] = pages
        return data, synthesis

    def no_markdown(question, *, config=None):
        raise AssertionError("markdown path must not run when output_schema is set")

    monkeypatch.setattr(mod, "structured_synthesis", fake_structured)
    monkeypatch.setattr(mod, "grounded_answer", no_markdown)
    state = ResearchTurnState(
        user_message="q",
        source="web",
        effort="fast",
        output_schema=output_schema,
        web_hits=WEB_HITS,
        web_pages=[
            _page("https://a.com/1", "A", "s a").model_dump(mode="json"),
            _page("https://b.com/2", "B", "s b").model_dump(mode="json"),
        ],
        usage=_retrieval_usage(),
    )
    out = mod.node_web_aggregate(state)

    assert seen["output_schema"] == output_schema
    assert seen["pages"] == [
        _page("https://a.com/1", "A", "s a"),
        _page("https://b.com/2", "B", "s b"),
    ]
    assert out["web_output"] == data.output
    assert out["results"][0]["score"] == 1.0
    assert out["results"][0]["engine"] == "searxng"
    assert out["usage"]["rerank_ms"] == 30
    assert out["usage"]["synthesis_ms"] == 7
    assert out["usage"]["llm_calls"] == 1
    assert out["cost_dollars"]["breakdown"]["pages_fetched"] == 5


def test_web_aggregate_passes_cited_pages_without_second_retrieval(monkeypatch):
    from digisearch.agent import web_branch as mod

    pages = [
        _page("https://a.com/1", "A", "s a"),
        _page("https://b.com/2", "B", "s b"),
    ]
    retrieval_calls: dict[str, int] = {"live": 0, "fetch": 0, "rank": 0}

    def count_live(*args: Any, **kwargs: Any) -> Any:
        retrieval_calls["live"] += 1
        raise AssertionError("web_aggregate must not search again")

    def count_fetch(*args: Any, **kwargs: Any) -> Any:
        retrieval_calls["fetch"] += 1
        raise AssertionError("web_aggregate must not fetch again")

    def count_rank(*args: Any, **kwargs: Any) -> Any:
        retrieval_calls["rank"] += 1
        raise AssertionError("web_aggregate must not rank again")

    monkeypatch.setattr(mod, "_live", count_live)
    monkeypatch.setattr(mod, "_fetch", count_fetch)
    monkeypatch.setattr(mod, "_rank", count_rank)
    seen: dict[str, Any] = {}

    def fake_grounded_answer(question, *, config=None, pages=None):
        seen["pages"] = pages
        return (
            WebSearchData(results=[], output={"text": "answer [1]"}),
            TurnUsage(llm_calls=1, synthesis_ms=5, total_ms=5),
        )

    monkeypatch.setattr(mod, "grounded_answer", fake_grounded_answer)
    state = ResearchTurnState(
        user_message="q",
        source="web",
        web_hits=WEB_HITS,
        web_pages=[page.model_dump(mode="json") for page in pages],
        usage=_retrieval_usage(),
    )
    out = mod.node_web_aggregate(state)

    assert seen["pages"] == pages  # rebuilt FetchedPage models, in retrieve order
    assert retrieval_calls == {"live": 0, "fetch": 0, "rank": 0}
    assert out["usage"]["searches"] == 1  # the one retrieval round, not undercounted
    assert out["usage"]["pages_fetched"] == 5
    assert out["usage"]["pages_cited"] == 2
    assert out["usage"]["llm_calls"] == 1


def test_web_aggregate_fail_hard_sets_error(monkeypatch):
    from digisearch.agent import web_branch as mod

    def boom(question, *, config=None, pages=None):
        raise WebResearchError("digillm down")

    monkeypatch.setattr(mod, "grounded_answer", boom)
    state = ResearchTurnState(user_message="q", source="web", web_hits=WEB_HITS)
    out = mod.node_web_aggregate(state)
    assert out["error"] is not None and "digillm down" in out["error"]
    assert out["trace"][0].step == "web_aggregate"
    assert out["trace"][0].status == "failed"


def test_run_web_research_turn_wires_retrieve_into_aggregate(monkeypatch):
    from digisearch.agent import web_branch as mod

    hits = [_hit("https://a.com/1", "A", score=0.8)]
    pages = [_page("https://a.com/1", "A", "body a")]
    monkeypatch.setattr(mod, "_live", lambda q, top_n: hits)
    monkeypatch.setattr(mod, "_fetch", lambda h, top_n: pages)
    monkeypatch.setattr(mod, "_rank", lambda q, p, top_n: pages)
    seen: dict[str, Any] = {}

    def fake_grounded_answer(question, *, config=None, pages=None):
        seen["pages"] = pages
        return (
            WebSearchData(results=[], output={"text": "answer [1]"}),
            TurnUsage(llm_calls=1, synthesis_ms=5, total_ms=5),
        )

    monkeypatch.setattr(mod, "grounded_answer", fake_grounded_answer)
    out = mod.run_web_research_turn({"user_message": "q", "source": "web", "effort": "fast"})

    assert seen["pages"] == pages  # the retrieve node's cited set, passed through as FetchedPage
    assert out["error"] is None
    assert out["backend"] == "web-oss"
    assert out["results"] == [
        {
            "url": "https://a.com/1",
            "title": "A",
            "snippet": "body a",
            "score": 0.8,
            "engine": "searxng",
            "metadata": {"evidence_tier": "External"},
        }
    ]
    assert out["rag_sources"][0]["doc_id"] == "https://a.com/1"
    assert out["formatted_context"] == "[1] https://a.com/1 — A — body a"
    assert out["usage"]["pages_fetched"] == 1
    assert out["usage"]["llm_calls"] == 1
    assert out["cost_dollars"]["provider"] == "web-oss"
    assert out["web_output"] == {"text": "answer [1]"}
    assert [step["step"] for step in out["trace"]] == ["plan", "web_retrieve", "web_aggregate"]


def test_web_hit_to_rag_row_preserves_url_and_tier():
    from digisearch.agent.web_branch import _web_hit_to_rag_row

    row = _web_hit_to_rag_row(WEB_HITS[0], 3)
    assert row == {
        "doc_id": "https://a.com/1",
        "content": "s a",
        "score": 1.0,
        "rank": 3,
        "metadata": {
            "source_url": "https://a.com/1",
            "title": "A",
            "engine": "searxng",
            "evidence_tier": "External",
        },
    }


def test_api_research_turn_web_passthrough(monkeypatch, client):
    from digisearch.agent import web_branch as mod

    pages = [
        {"url": "https://a.com/1", "title": "A", "snippet": "s", "score": 1.0, "engine": "searxng"}
    ]
    seen: dict[str, Any] = {}

    def fake_retrieve(state):
        seen["source"] = state.source
        seen["effort"] = state.effort
        seen["cited_top_n"] = state.cited_top_n
        seen["output_schema"] = state.output_schema
        return {"web_hits": pages}

    monkeypatch.setattr(mod, "node_web_retrieve", fake_retrieve)
    monkeypatch.setattr(
        mod,
        "node_web_aggregate",
        lambda s: {
            "backend": "web-oss",
            "results": [{**pages[0], "metadata": {"evidence_tier": "External"}}],
            "formatted_context": "[1] https://a.com/1 — A",
            "web_output": {"text": "answer [1]"},
            "cost_dollars": {
                "total": 0.0,
                "provider": "web-oss",
                "breakdown": {"searches": 1, "pages_fetched": 1, "llm_calls": 1},
                "note": "oss-synthesis; llm spend metered in digillm telemetry, not here",
            },
            "usage": {"searches": 1},
        },
    )
    resp = client.post(
        "/v1/research_turn",
        json={
            "user_message": "q",
            "source": "web",
            "effort": "thorough",
            "cited_top_n": 2,
            "output_schema": {"type": "object"},
        },
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["backend"] == "web-oss"
    assert data["results"][0]["metadata"]["evidence_tier"] == "External"
    assert data["cost_dollars"]["provider"] == "web-oss"
    assert data["cost_dollars"]["breakdown"]["llm_calls"] == 1
    assert data["usage"] == {"searches": 1}
    assert data["error"] is None
    assert seen == {
        "source": "web",
        "effort": "thorough",
        "cited_top_n": 2,
        "output_schema": {"type": "object"},
    }


def test_api_research_turn_source_defaults_to_corpus(monkeypatch, client):
    from digisearch.agent import web_branch as mod

    def boom(state):
        raise AssertionError("web branch must not run for the corpus default")

    monkeypatch.setattr(mod, "node_web_retrieve", boom)
    idx = "__agent_http_corpus_default__"
    add_chunks(
        idx,
        [
            Chunk(
                id="c9",
                content="Risk parity overview",
                doc_id="doc-rp",
                embedding=None,
                metadata={"sourceType": "PDF"},
            )
        ],
    )
    resp = client.post(
        "/v1/research_turn",
        json={"user_message": "risk", "index_name": idx, "top_k": 3},
    )
    assert resp.status_code == 200, resp.text
    data = resp.json()
    assert data["rag_sources"]
    assert "Risk parity" in data["formatted_context"]
    assert data["backend"] != "web-oss"
    assert data["cost_dollars"] is None
    assert data["usage"] is None
    assert data["web_output"] is None


def test_api_research_turn_rejects_unknown_source(client):
    resp = client.post("/v1/research_turn", json={"user_message": "q", "source": "sneaky"})
    assert resp.status_code == 422


def test_mcp_research_turn_forwards_source_and_effort(monkeypatch):
    pytest.importorskip("mcp.server.fastmcp")
    from digisearch import mcp_server

    seen: dict[str, Any] = {}

    def fake_run(payload):
        seen.update(payload)
        return {"service": "digisearch"}

    monkeypatch.setattr(mcp_server, "_run_research_turn", fake_run)
    out = mcp_server.digisearch_research_turn(user_message="q", source="web", effort="thorough")
    assert seen["source"] == "web"
    assert seen["effort"] == "thorough"
    assert '"service": "digisearch"' in out


def test_research_delegate_manifest_exposes_web_fields():
    from digisearch.orchestrator_tools import build_digisearch_research_delegate_tool

    props = build_digisearch_research_delegate_tool()["function"]["parameters"]["properties"]
    assert props["source"]["enum"] == ["corpus", "web", "auto"]
    assert props["effort"]["enum"] == ["fast", "thorough"]
    assert props["output_schema"]["type"] == "object"


def test_web_package_root_keeps_synthesis_lazy():
    import digisearch.web as web_pkg

    tree = ast.parse(inspect.getsource(web_pkg))
    module_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            module_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_imports.add(node.module)
    assert "digisearch.web.answer" not in module_imports
    assert "digisearch.web.structured" not in module_imports


def test_web_package_resolves_lazy_exports():
    import digisearch.web as web_pkg
    from digisearch.web import answer as answer_mod
    from digisearch.web import structured as structured_mod

    assert web_pkg.grounded_answer is answer_mod.grounded_answer
    assert web_pkg.structured_synthesis is structured_mod.structured_synthesis
    assert web_pkg.verify_grounding is structured_mod.verify_grounding
    assert "grounded_answer" in web_pkg.__all__
    assert "structured_synthesis" in web_pkg.__all__
    with pytest.raises(AttributeError):
        web_pkg.not_a_real_export
