"""Offline tests for the Phase B structured synthesis path (#4064).

Every external boundary is mocked: ``_retrieve_cited`` (or its ``_live`` /
``_fetch`` / ``_rank`` seams) and ``digillm.client.completion``. No network,
no model weights, no rank_bm25.
"""

from __future__ import annotations

import ast
import inspect
import json
import types
from typing import Any

import pytest
from digisearch.web.retrieve import FetchedPage
from digisearch.web_search.models import WebSearchResult

pytestmark = pytest.mark.unit


def _page(url: str, title: str = "", markdown: str = "") -> FetchedPage:
    return FetchedPage(url=url, title=title, markdown=markdown or f"page body for {url}")


def _completion(text: str) -> Any:
    """Minimal duck-typed ChatCompletion: only choices[0].message.content is read."""
    message = types.SimpleNamespace(content=text)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _synthesis(payload: dict[str, Any]) -> Any:
    return _completion(json.dumps(payload))


# ── the brief's two acceptance tests ──────────────────────────────────────────


def test_verify_downgrades_echo_and_flags_uncited():
    from digisearch.web.structured import verify_grounding

    content = {"companies": [{"name": "SpaceX", "launcher": "SpaceX"}]}
    grounding = [
        {
            "field": "companies[0].name",
            "citations": [{"url": "https://a.com/1", "title": "A"}],
            "confidence": "high",
        },
        {
            "field": "companies[0].launcher",
            "citations": [{"url": "https://a.com/1", "title": "A"}],
            "confidence": "high",
        },
        {
            "field": "companies[0].vehicles",
            "citations": [{"url": "https://ghost.example/x", "title": "X"}],
            "confidence": "high",
        },
    ]
    out = verify_grounding(content, grounding, cited_urls={"https://a.com/1"})
    by_field = {g["field"] if isinstance(g, dict) else g.field: g for g in out}

    def conf(g):
        return g["confidence"] if isinstance(g, dict) else g.confidence.value

    assert conf(by_field["companies[0].launcher"]) == "medium"
    assert conf(by_field["companies[0].vehicles"]) == "unverified"
    assert conf(by_field["companies[0].name"]) == "high"


def test_structured_synthesis_rejects_partial_content(monkeypatch):
    import pytest
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchError

    pages = [{"url": "https://a.com/1", "title": "A", "markdown": "page body"}]
    # Retrieval SUCCEEDS (non-empty cited set) so the test exercises the
    # missing-required-key path — NOT the zero-pages raise.
    monkeypatch.setattr(mod, "_retrieve_cited", lambda q, cfg: (pages, {"https://a.com/1"}))
    monkeypatch.setattr(
        mod,
        "_synthesize_structured",
        lambda q, pages, schema, cfg: (
            {"other": []},  # missing required "rounds"
            [
                {
                    "field": "other[0]",
                    "citations": [{"url": "https://a.com/1", "title": "A", "excerpt": "e"}],
                    "confidence": "high",
                }
            ],
            "text",
        ),
    )
    with pytest.raises(WebResearchError):
        mod.structured_synthesis("q", output_schema={"required": ["rounds"]})


# ── verify_grounding: pure pass, model + dict input ───────────────────────────


def test_verify_returns_field_grounding_models_for_model_input():
    from digisearch.web.grounding_models import Confidence, FieldGrounding
    from digisearch.web.structured import verify_grounding
    from digisearch.web_search.citation import Citation

    content = {"companies": [{"name": "SpaceX", "launcher": "SpaceX"}]}
    grounding = [
        FieldGrounding(
            field="companies[0].name",
            citations=[Citation(url="https://a.com/1", title="A")],
            confidence=Confidence.HIGH,
        ),
        FieldGrounding(
            field="companies[0].launcher",
            citations=[Citation(url="https://a.com/1", title="A")],
            confidence=Confidence.HIGH,
        ),
    ]
    out = verify_grounding(content, grounding, cited_urls={"https://a.com/1"})

    assert all(isinstance(entry, FieldGrounding) for entry in out)
    assert all(isinstance(entry.citations[0], Citation) for entry in out)
    assert [entry.field for entry in out] == ["companies[0].name", "companies[0].launcher"]
    assert out[0].confidence is Confidence.HIGH
    assert out[1].confidence is Confidence.MEDIUM


def test_verify_drops_entries_outside_the_content_structure():
    from digisearch.web.structured import verify_grounding

    content = {"companies": [{"name": "Wafer"}]}
    grounding = [
        {"field": "companies[0].name", "citations": [], "confidence": "high"},
        {"field": "companies[7].name", "citations": [], "confidence": "high"},
        {"field": "funding.round", "citations": [], "confidence": "high"},
        {"field": "companies[0].name.extra", "citations": [], "confidence": "high"},
    ]
    out = verify_grounding(content, grounding, cited_urls=set())

    assert [entry["field"] for entry in out] == ["companies[0].name"]
    assert out[0]["confidence"] == "unverified"  # zero citations -> flagged, kept


def test_verify_never_raises_on_loose_input():
    from digisearch.web.structured import verify_grounding

    loose: list[Any] = [
        None,
        "nope",
        7,
        {},
        {"field": ""},
        {"field": "a", "citations": "not-a-list", "confidence": "certain"},
        {"field": "a", "citations": [{"nope": 1}, "https://a.com/1"], "confidence": "high"},
    ]
    out = verify_grounding({"a": 1}, loose, cited_urls={"https://a.com/1"})
    assert verify_grounding({"a": 1}, None, cited_urls=set()) == []

    by_field = [entry for entry in out if entry["field"] == "a"]
    assert len(by_field) == 2
    assert by_field[0]["confidence"] == "unverified"  # unknown confidence is never verified
    assert by_field[0]["citations"] == []
    assert by_field[1]["confidence"] == "unverified"  # loose citations match nothing
    assert by_field[1]["citations"] == [{"nope": 1}, {}]


def test_verify_keeps_cited_irrelevant_at_model_confidence():
    from digisearch.web.structured import verify_grounding

    content = {"answer": "The capital of France is Paris."}
    grounding = [
        {
            "field": "answer",
            "citations": [{"url": "https://irrelevant.example/x", "title": "Irrelevant"}],
            "confidence": "low",
        }
    ]
    out = verify_grounding(content, grounding, cited_urls={"https://irrelevant.example/x"})

    # Cited-but-irrelevant is NOT detected: the model-assigned confidence stays.
    assert out[0]["confidence"] == "low"


def test_verify_echo_downgrade_chain_reaches_unverified():
    from digisearch.web.structured import verify_grounding

    content = {"a": "X", "b": "X", "c": "X", "d": "X"}
    cited = {"url": "https://a.com/1"}
    grounding = [
        {"field": field, "citations": [dict(cited)], "confidence": confidence}
        for field, confidence in (("a", "high"), ("b", "high"), ("c", "medium"), ("d", "low"))
    ]
    out = verify_grounding(content, grounding, cited_urls={"https://a.com/1"})

    # The first sibling to claim a value keeps its confidence; each later echo
    # is downgraded one level (high -> medium -> low -> unverified).
    assert [entry["confidence"] for entry in out] == [
        "high",
        "medium",
        "low",
        "unverified",
    ]


# ── _retrieve_cited: reuses the landed Task 3 pipeline ────────────────────────


def test_retrieve_cited_reuses_rank_with_config_budgets(monkeypatch):
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig

    hits = [
        WebSearchResult(url="https://a.com/1", title="A", snippet="s", score=0.9, engine="searxng")
    ]
    seen: dict[str, int] = {}

    def fake_live(query: str, top_n: int) -> list[WebSearchResult]:
        seen["live_top_n"] = top_n
        return hits

    def fake_fetch(hit_rows: list[WebSearchResult], top_n: int) -> list[FetchedPage]:
        seen["fetch_top_n"] = top_n
        return [_page(hit.url, hit.title) for hit in hit_rows]

    def fake_rank(query: str, pages: list[FetchedPage], top_n: int) -> list[FetchedPage]:
        seen["cited_top_n"] = top_n
        return pages

    monkeypatch.setattr(mod, "_live", fake_live)
    monkeypatch.setattr(mod, "_fetch", fake_fetch)
    monkeypatch.setattr(mod, "_rank", fake_rank)

    cited, cited_urls = mod._retrieve_cited(
        "q", WebResearchConfig(live_top_n=3, fetch_top_n=2, cited_top_n=1)
    )

    assert seen == {"live_top_n": 3, "fetch_top_n": 2, "cited_top_n": 1}
    assert [page.url for page in cited] == ["https://a.com/1"]
    assert cited_urls == {"https://a.com/1"}


def test_retrieve_cited_raises_when_rank_drops_all_sources(monkeypatch):
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig, WebResearchError

    monkeypatch.setattr(mod, "_live", lambda q, top_n: [])
    monkeypatch.setattr(mod, "_fetch", lambda hits, top_n: [])
    monkeypatch.setattr(mod, "_rank", lambda q, pages, top_n: [])

    with pytest.raises(WebResearchError):
        mod._retrieve_cited("q", WebResearchConfig())


def test_structured_synthesis_raises_when_retrieval_yields_no_sources(monkeypatch):
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchError

    monkeypatch.setattr(
        mod,
        "_live",
        lambda q, top_n: [WebSearchResult(url="https://a.com/1", title="A", snippet="s")],
    )
    monkeypatch.setattr(mod, "_fetch", lambda hits, top_n: [_page("https://a.com/1", "A")])
    monkeypatch.setattr(mod, "_rank", lambda q, pages, top_n: [])

    with pytest.raises(WebResearchError):
        mod.structured_synthesis("q", output_schema={"required": []})


# ── _synthesize_structured: digillm wrapper contract + fail-hard parsing ──────


def test_synthesize_structured_requires_synthesis_model_env(monkeypatch):
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchError

    monkeypatch.delenv("DIGISEARCH_SYNTHESIS_MODEL", raising=False)
    monkeypatch.setattr(
        mod,
        "_retrieve_cited",
        lambda q, cfg: ([_page("https://a.com/1", "A")], {"https://a.com/1"}),
    )

    with pytest.raises(WebResearchError) as excinfo:
        mod.structured_synthesis("q", output_schema={"required": []})

    assert "DIGISEARCH_SYNTHESIS_MODEL" in str(excinfo.value)


def test_synthesize_structured_sends_wrapper_schema_and_numbered_sources(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import FieldGrounding, WebResearchConfig

    schema = {
        "type": "object",
        "required": ["rounds"],
        "properties": {"rounds": {"type": "array", "items": {"type": "object"}}},
    }
    payload = {
        "content": {"rounds": []},
        "grounding": [
            {
                "field": "rounds",
                "citations": [{"url": "https://a.com/1", "title": "A", "excerpt": "e"}],
                "confidence": "high",
            }
        ],
    }
    calls: dict[str, Any] = {}

    def fake_completion(model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        calls["model"] = model
        calls["messages"] = messages
        calls["kwargs"] = kwargs
        return _synthesis(payload)

    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", fake_completion)

    content, grounding, text = mod._synthesize_structured(
        "Series A?", [_page("https://a.com/1", "A", markdown="body")], schema, WebResearchConfig()
    )

    assert content == {"rounds": []}
    assert text == json.dumps(payload)  # model message text (the wrapper JSON)
    assert all(isinstance(entry, FieldGrounding) for entry in grounding)
    assert grounding[0].field == "rounds"
    assert grounding[0].citations[0].url == "https://a.com/1"

    assert calls["model"] == "openai/gpt-4o-mini"
    assert calls["kwargs"]["usage_kind"] == "web_search"
    response_format = calls["kwargs"]["response_format"]
    assert response_format["type"] == "json_schema"
    assert response_format["json_schema"]["name"] == "web_structured"
    wrapper = response_format["json_schema"]["schema"]
    assert wrapper["properties"]["content"] is schema  # caller schema, never a copy
    assert wrapper["required"] == ["content", "grounding"]
    assert wrapper["additionalProperties"] is False
    entry = wrapper["properties"]["grounding"]["items"]
    assert entry["required"] == ["field", "citations", "confidence"]
    assert entry["properties"]["confidence"]["enum"] == ["high", "medium", "low"]
    assert entry["properties"]["citations"]["items"]["required"] == ["url"]

    system = calls["messages"][0]["content"]
    user = calls["messages"][1]["content"]
    assert calls["messages"][0]["role"] == "system"
    assert calls["messages"][1]["role"] == "user"
    assert "grounding" in system
    assert "[1] https://a.com/1" in user
    assert "Series A?" in user
    assert json.dumps(schema, sort_keys=True) in user


def test_synthesize_structured_rejects_unparseable_response(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig, WebResearchError

    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _completion("not json"))

    with pytest.raises(WebResearchError):
        mod._synthesize_structured(
            "q", [_page("https://a.com/1", "A")], {"required": []}, WebResearchConfig()
        )


def test_synthesize_structured_rejects_payload_without_citation_url(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig, WebResearchError

    payload = {
        "content": {"a": 1},
        "grounding": [{"field": "a", "citations": [{"title": "no url"}], "confidence": "high"}],
    }
    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _synthesis(payload))

    with pytest.raises(WebResearchError):
        mod._synthesize_structured(
            "q", [_page("https://a.com/1", "A")], {"required": ["a"]}, WebResearchConfig()
        )


def test_synthesize_structured_truncated_source_is_not_verified(monkeypatch):
    """A source truncated out of the prompt is not citable (fail-safe direction)."""
    import digillm.client as digillm_client
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig

    payload = {
        "content": {"round": "Series A"},
        "grounding": [
            {
                "field": "round",
                "citations": [{"url": "https://b.com/2", "title": "B"}],
                "confidence": "high",
            }
        ],
    }
    calls: dict[str, Any] = {}

    def fake_completion(model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        calls["messages"] = messages
        return _synthesis(payload)

    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", fake_completion)
    pages = [
        _page("https://a.com/1", "A", markdown="x" * 3000),
        _page("https://b.com/2", "B", markdown="y" * 3000),
    ]

    content, grounding, _text = mod._synthesize_structured(
        "q", pages, {"required": ["round"]}, WebResearchConfig(max_synthesis_chars=1500)
    )

    user = calls["messages"][1]["content"]
    assert "https://b.com/2" not in user  # budget-truncated out of the numbered sources
    assert content == {"round": "Series A"}
    assert grounding[0].citations[0].url == "https://b.com/2"
    assert grounding[0].confidence.value == "unverified"  # never seen by the model


# ── structured_synthesis: EXA-shaped envelope (s4 echo + g2 multi-field) ──────


def test_structured_synthesis_envelope_mirrors_exa_shape(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig

    from digisearch import web_exa

    payload = {
        "content": {"companies": [{"name": "SpaceX", "launcher": "SpaceX"}]},
        "grounding": [
            {
                "field": "companies[0].name",
                "citations": [{"url": "https://a.com/1", "title": "A"}],
                "confidence": "high",
            },
            {
                "field": "companies[0].launcher",
                "citations": [{"url": "https://a.com/1", "title": "A"}],
                "confidence": "high",
            },
            {
                "field": "companies[0].vehicles",
                "citations": [{"url": "https://ghost.example/x", "title": "X"}],
                "confidence": "high",
            },
        ],
    }
    pages = [_page("https://a.com/1", "A", markdown="page body")]
    monkeypatch.setattr(mod, "_retrieve_cited", lambda q, cfg: (pages, {"https://a.com/1"}))
    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _synthesis(payload))

    data, usage = mod.structured_synthesis(
        "Which launcher?", output_schema={"required": ["companies"]}, config=WebResearchConfig()
    )

    assert isinstance(data, web_exa.WebSearchData)
    assert data.output["content"] == payload["content"]
    assert data.output["text"] == json.dumps(payload)
    rows = {row["field"]: row for row in data.output["grounding"]}
    assert rows["companies[0].name"]["confidence"] == "high"
    assert rows["companies[0].launcher"]["confidence"] == "medium"
    assert rows["companies[0].vehicles"]["confidence"] == "unverified"
    assert rows["companies[0].name"]["citations"][0] == {
        "url": "https://a.com/1",
        "title": "A",
        "excerpt": "",
    }
    assert rows["companies[0].vehicles"]["citations"][0]["url"] == "https://ghost.example/x"

    assert data.search_type == "web-fast"
    assert data.results == [
        {
            "title": "A",
            "url": "https://a.com/1",
            "snippet": "page body",
            "score": 0.0,
            "engine": "",
        }
    ]
    assert data.cost_dollars == {
        "total": 0.0,
        "provider": "web-oss",
        "breakdown": {"searches": 1, "pages_fetched": 1, "llm_calls": 1},
        "note": "oss-synthesis; llm spend metered in digillm telemetry, not here",
    }
    assert usage.searches == 1
    assert usage.pages_fetched == 1
    assert usage.pages_cited == 1
    assert usage.llm_calls == 1
    assert usage.total_ms == usage.rerank_ms + usage.synthesis_ms


def test_structured_synthesis_g2_multi_field_fixture_keeps_citations(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig

    content = {
        "company": {"name": "Wafer Systems", "founded": "2019"},
        "funding": {"round": "Series A", "amount": "$40M"},
        "investors": [{"name": "Aperture Capital"}, {"name": "Nimbus Ventures"}],
    }
    field_urls = [
        ("company.name", "https://a.com/1"),
        ("company.founded", "https://b.com/2"),
        ("funding.round", "https://a.com/1"),
        ("funding.amount", "https://b.com/2"),
        ("investors[0].name", "https://a.com/1"),
        ("investors[1].name", "https://b.com/2"),
    ]
    payload = {
        "content": content,
        "grounding": [
            {"field": field, "citations": [{"url": url, "title": url}], "confidence": "high"}
            for field, url in field_urls
        ],
    }
    pages = [_page("https://a.com/1", "A"), _page("https://b.com/2", "B")]
    monkeypatch.setattr(
        mod, "_retrieve_cited", lambda q, cfg: (pages, {"https://a.com/1", "https://b.com/2"})
    )
    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _synthesis(payload))

    data, _usage = mod.structured_synthesis(
        "Wafer Systems funding?",
        output_schema={"required": ["company", "funding", "investors"]},
        config=WebResearchConfig(),
    )

    rows = {row["field"]: row for row in data.output["grounding"]}
    assert set(rows) == {field for field, _ in field_urls}
    for field, url in field_urls:
        assert [citation["url"] for citation in rows[field]["citations"]] == [url]
        assert rows[field]["confidence"] == "high"
    assert data.output["content"] == content


# ── structured_synthesis: supplied-pages seam (#4084) ─────────────────────────


def test_structured_synthesis_supplied_pages_skips_retrieval(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchConfig

    def explode(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("_retrieve_cited must not run when pages are supplied")

    monkeypatch.setattr(mod, "_retrieve_cited", explode)
    monkeypatch.setattr(mod, "_live", explode)
    monkeypatch.setattr(mod, "_fetch", explode)
    monkeypatch.setattr(mod, "_rank", explode)
    payload = {
        "content": {"round": "Series A"},
        "grounding": [
            {
                "field": "round",
                "citations": [{"url": "https://a.com/1", "title": "A"}],
                "confidence": "high",
            }
        ],
    }
    pages = [_page("https://a.com/1", "A", markdown="page body")]
    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _synthesis(payload))

    data, usage = mod.structured_synthesis(
        "q", output_schema={"required": ["round"]}, config=WebResearchConfig(), pages=pages
    )

    assert data.output["content"] == {"round": "Series A"}
    assert data.results == [
        {
            "title": "A",
            "url": "https://a.com/1",
            "snippet": "page body",
            "score": 0.0,
            "engine": "",
        }
    ]
    assert data.cost_dollars["breakdown"] == {"searches": 0, "pages_fetched": 0, "llm_calls": 1}
    assert usage.searches == 0
    assert usage.pages_fetched == 0
    assert usage.pages_cited == 1
    assert usage.llm_calls == 1
    assert usage.rerank_ms == 0
    assert usage.total_ms == usage.synthesis_ms


def test_structured_synthesis_empty_supplied_pages_fails_hard(monkeypatch):
    from digisearch.web import structured as mod
    from digisearch.web.grounding_models import WebResearchError

    monkeypatch.setattr(
        mod, "_retrieve_cited", lambda q, cfg: pytest.fail("must not retrieve when pages are given")
    )
    with pytest.raises(WebResearchError) as excinfo:
        mod.structured_synthesis("q", output_schema={"required": []}, pages=[])
    assert "no citable sources" in str(excinfo.value)


# ── module discipline pins ────────────────────────────────────────────────────


def test_structured_module_never_indexes_and_reuses_rank():
    from digisearch.web import structured as mod

    source = inspect.getsource(mod)
    assert "ingest_url" not in source  # it indexes (R3)
    assert "ingest_source" not in source
    assert "def _rank" not in source  # Task 3 ranking is imported, never copied
    assert "from digisearch.web.answer import" in source


def test_structured_module_scope_keeps_optional_deps_lazy():
    from digisearch.web import structured as mod

    tree = ast.parse(inspect.getsource(mod))
    module_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            module_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_imports.add(node.module)
    forbidden = (
        "digifetch",
        "digillm",
        "sentence_transformers",
        "chonkie",
        "rank_bm25",
        "digisearch.chunking",
        "digisearch.search.keyword",
        "digisearch.search.reranker",
    )
    for lazy_only in forbidden:
        assert not any(
            name == lazy_only or name.startswith(f"{lazy_only}.") for name in module_imports
        ), f"{lazy_only} must be imported lazily, inside the seam that uses it"
