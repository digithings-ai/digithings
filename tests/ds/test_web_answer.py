"""Offline tests for the Phase B ``grounded_answer`` loop (#4064).

Every external boundary is mocked: the four module seams (``_live``,
``_fetch``, ``_rank``, ``_synthesize``), the chunker factory, BM25, BGE, and
``digillm.client.completion``. No network, no model weights, no rank_bm25.
"""

from __future__ import annotations

import importlib.machinery
import importlib.util
import logging
import sys
import types
from typing import Any

import pytest
from digisearch.core.models import Chunk, Document, Query, Result
from digisearch.web.retrieve import FetchedPage
from digisearch.web_search.models import WebSearchResult

pytestmark = pytest.mark.unit


def _hit(url: str, title: str, score: float = 0.9, engine: str = "searxng") -> WebSearchResult:
    return WebSearchResult(url=url, title=title, snippet=f"snip {url}", score=score, engine=engine)


def _page(url: str, title: str = "", markdown: str = "") -> FetchedPage:
    return FetchedPage(url=url, title=title, markdown=markdown or f"page body for {url}")


def _completion(text: str) -> Any:
    """Minimal duck-typed ChatCompletion: only choices[0].message.content is read."""
    message = types.SimpleNamespace(content=text)
    return types.SimpleNamespace(choices=[types.SimpleNamespace(message=message)])


def _fake_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``importlib.util.find_spec("sentence_transformers")`` non-None."""
    fake = types.ModuleType("sentence_transformers")
    fake.__spec__ = importlib.machinery.ModuleSpec("sentence_transformers", loader=None)
    monkeypatch.setitem(sys.modules, "sentence_transformers", fake)


def _hide_sentence_transformers(monkeypatch: pytest.MonkeyPatch) -> None:
    """Make ``importlib.util.find_spec("sentence_transformers")`` None everywhere."""
    real_find_spec = importlib.util.find_spec

    def find_spec(name: str, *args: Any, **kwargs: Any) -> Any:
        if name == "sentence_transformers":
            return None
        return real_find_spec(name, *args, **kwargs)

    monkeypatch.setattr(importlib.util, "find_spec", find_spec)


class _FakeChunker:
    """One chunk per document by default; content tags the parent document."""

    def __init__(self, chunks_per_doc: int = 1) -> None:
        self.chunks_per_doc = chunks_per_doc

    def chunk(self, doc: Document) -> list[Chunk]:
        return [
            Chunk(id=f"{doc.id}#{i}", content=f"chunk {i} of {doc.id}", doc_id=doc.id)
            for i in range(self.chunks_per_doc)
        ]


def _fake_bm25(script: list[tuple[int, float]], seen: dict[str, Any]) -> type:
    """BM25Searcher factory: returns scripted (corpus_index, score) hits."""

    class _FakeBM25Searcher:
        def __init__(self, corpus: list[str]) -> None:
            self._corpus = list(corpus)
            seen["corpus"] = list(corpus)

        def search(self, query: Query, top_k: int | None = None) -> list[Result]:
            seen["query"] = query.text
            seen["top_k"] = top_k
            limit = top_k if top_k is not None else len(script)
            return [
                Result(
                    chunk=Chunk(id=str(idx), content=self._corpus[idx], doc_id=""),
                    score=score,
                    rank=rank,
                )
                for rank, (idx, score) in enumerate(script[:limit], 1)
            ]

    return _FakeBM25Searcher


def _recording_reranker(seen: dict[str, Any], order: list[int] | None = None) -> type:
    """Reranker factory: records candidates/top_n, returns them in *order*."""

    class _RecordingReranker:
        def __init__(
            self, provider: str = "cohere", top_n: int | None = None, strict: bool = False
        ) -> None:
            seen["provider"] = provider
            seen["ctor_top_n"] = top_n
            seen["strict"] = strict

        def rerank(
            self, query: str, results: list[Result], top_n: int | None = None
        ) -> list[Result]:
            seen["query"] = query
            seen["candidates"] = list(results)
            seen["top_n"] = top_n
            ranked = [results[i] for i in order] if order is not None else list(results)
            limit = top_n if top_n is not None else len(ranked)
            return ranked[:limit]

    return _RecordingReranker


# ── the brief's two acceptance tests ──────────────────────────────────────────


def test_grounded_answer_cites_every_claim(monkeypatch):
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchConfig

    from digisearch import web_exa

    monkeypatch.setattr(
        mod,
        "_live",
        lambda q, top_n: [
            WebSearchResult(
                url="https://a.com/1", title="A", snippet="s1", score=0.9, engine="searxng"
            ),
            WebSearchResult(
                url="https://b.com/2", title="B", snippet="s2", score=0.8, engine="searxng"
            ),
        ],
    )
    monkeypatch.setattr(
        mod,
        "_fetch",
        lambda hits, top_n: [
            FetchedPage(url=h.url, title=h.title, markdown=f"page body for {h.url}") for h in hits
        ],
    )
    monkeypatch.setattr(mod, "_rank", lambda q, pages, top_n: pages[:1])
    monkeypatch.setattr(
        mod, "_synthesize", lambda q, pages, cfg: ("Wafer raised $40M [1].", {"llm_calls": 1})
    )
    data, usage = mod.grounded_answer("Series A AI infra rounds", config=WebResearchConfig())
    assert isinstance(data, web_exa.WebSearchData)
    assert "[1]" in str(data.output.get("text"))
    assert data.results[0]["url"] == "https://a.com/1"
    assert usage.llm_calls == 1


def test_grounded_answer_raises_on_zero_pages(monkeypatch):
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchError

    monkeypatch.setattr(mod, "_live", lambda q, top_n: [])
    with pytest.raises(WebResearchError):
        mod.grounded_answer("anything")


def test_grounded_answer_raises_when_rank_drops_all_sources(monkeypatch):
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchError

    monkeypatch.setattr(mod, "_live", lambda q, top_n: [_hit("https://a.com/1", "A")])
    monkeypatch.setattr(mod, "_fetch", lambda hits, top_n: [_page(h.url, h.title) for h in hits])
    monkeypatch.setattr(mod, "_rank", lambda q, pages, top_n: [])
    with pytest.raises(WebResearchError):
        mod.grounded_answer("q")


# ── envelope + accounting assembly ────────────────────────────────────────────


def test_grounded_answer_envelope_mirrors_exa_shape(monkeypatch):
    from digisearch.web import answer as mod

    hits = [
        _hit("https://a.com/1", "A", score=0.9, engine="searxng"),
        _hit("https://b.com/2", "B", score=0.8, engine="ddgs"),
    ]
    pages = [_page("https://a.com/1", "A", markdown="alpha body"), _page("https://b.com/2", "B")]
    monkeypatch.setattr(mod, "_live", lambda q, top_n: hits)
    monkeypatch.setattr(mod, "_fetch", lambda h, top_n: pages)
    monkeypatch.setattr(mod, "_rank", lambda q, p, top_n: p)
    monkeypatch.setattr(mod, "_synthesize", lambda q, p, cfg: ("answer [1][2]", {"llm_calls": 1}))

    data, usage = mod.grounded_answer("q")

    assert data.output == {"text": "answer [1][2]"}
    assert data.search_type == "web-fast"
    assert data.cost_dollars == {
        "total": 0.0,
        "provider": "web-oss",
        "breakdown": {"searches": 1, "pages_fetched": 2, "llm_calls": 1},
        "note": "oss-synthesis; llm spend metered in digillm telemetry, not here",
    }
    assert [r["url"] for r in data.results] == ["https://a.com/1", "https://b.com/2"]
    assert set(data.results[0]) == {"title", "url", "snippet", "score", "engine"}
    assert data.results[0]["title"] == "A"
    assert data.results[0]["snippet"] == "alpha body"
    assert data.results[0]["score"] == 0.9
    assert data.results[0]["engine"] == "searxng"
    assert data.results[1]["engine"] == "ddgs"
    assert usage.searches == 1
    assert usage.pages_fetched == 2
    assert usage.pages_cited == 2
    assert usage.llm_calls == 1
    assert usage.total_ms == (
        usage.search_ms + usage.fetch_ms + usage.rerank_ms + usage.synthesis_ms
    )


def test_grounded_answer_snippet_is_capped_at_2000_chars(monkeypatch):
    from digisearch.web import answer as mod

    monkeypatch.setattr(mod, "_live", lambda q, top_n: [_hit("https://a.com/1", "A")])
    monkeypatch.setattr(
        mod, "_fetch", lambda h, top_n: [_page("https://a.com/1", "A", markdown="x" * 5000)]
    )
    monkeypatch.setattr(mod, "_rank", lambda q, p, top_n: p)
    monkeypatch.setattr(mod, "_synthesize", lambda q, p, cfg: ("answer [1]", {"llm_calls": 1}))

    data, _ = mod.grounded_answer("q")
    assert len(data.results[0]["snippet"]) == 2000


def test_grounded_answer_uses_config_budgets_and_effort_label(monkeypatch):
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import EFFORT_PRESETS, EffortMode

    seen: dict[str, Any] = {}

    def fake_live(q: str, top_n: int) -> list[WebSearchResult]:
        seen["live_top_n"] = top_n
        return [_hit("https://a.com/1", "A")]

    def fake_fetch(hits: list[WebSearchResult], top_n: int) -> list[FetchedPage]:
        seen["fetch_top_n"] = top_n
        return [_page(h.url, h.title) for h in hits]

    def fake_rank(q: str, pages: list[FetchedPage], top_n: int) -> list[FetchedPage]:
        seen["cited_top_n"] = top_n
        return pages

    monkeypatch.setattr(mod, "_live", fake_live)
    monkeypatch.setattr(mod, "_fetch", fake_fetch)
    monkeypatch.setattr(mod, "_rank", fake_rank)
    monkeypatch.setattr(mod, "_synthesize", lambda q, p, cfg: ("answer [1]", {"llm_calls": 1}))

    fast, _ = mod.grounded_answer("q")
    assert fast.search_type == "web-fast"
    assert seen == {
        "live_top_n": EFFORT_PRESETS[EffortMode.FAST].live_top_n,
        "fetch_top_n": EFFORT_PRESETS[EffortMode.FAST].fetch_top_n,
        "cited_top_n": EFFORT_PRESETS[EffortMode.FAST].cited_top_n,
    }

    thorough = EFFORT_PRESETS[EffortMode.THOROUGH].model_copy(update={"cited_top_n": 3})
    thorough_out, _ = mod.grounded_answer("q", config=thorough)
    assert thorough_out.search_type == "web-thorough"
    assert seen["live_top_n"] == 20
    assert seen["fetch_top_n"] == 10
    assert seen["cited_top_n"] == 3


# ── _rank: chunk -> BM25 (optional) -> BGE (fail-hard) ────────────────────────


def test_rank_requires_rerank_extra_before_touching_reranker(monkeypatch):
    from digisearch.chunking import factory as factory_mod
    from digisearch.search import reranker as reranker_mod
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchError

    monkeypatch.setattr(factory_mod, "get_document_chunker", lambda: _FakeChunker())
    _hide_sentence_transformers(monkeypatch)

    def explode(*args: Any, **kwargs: Any) -> None:
        raise AssertionError("Reranker must not be reached before the BGE guard")

    monkeypatch.setattr(reranker_mod, "Reranker", explode)
    with pytest.raises(WebResearchError) as excinfo:
        mod._rank("q", [_page("https://a.com/1", "A", markdown="body")], 5)
    assert "digisearch[rerank]" in str(excinfo.value)


def test_rank_surfaces_bge_rerank_failure_as_web_research_error(monkeypatch):
    from digisearch.chunking import factory as factory_mod
    from digisearch.search import reranker as reranker_mod
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchError

    monkeypatch.setattr(factory_mod, "get_document_chunker", lambda: _FakeChunker())
    _fake_sentence_transformers(monkeypatch)
    seen: dict[str, Any] = {}

    class _ExplodingReranker:
        def __init__(
            self, provider: str = "cohere", top_n: int | None = None, strict: bool = False
        ) -> None:
            seen["provider"] = provider
            seen["strict"] = strict

        def rerank(
            self, query: str, results: list[Result], top_n: int | None = None
        ) -> list[Result]:
            raise RuntimeError("cross-encoder load failed")

    monkeypatch.setattr(reranker_mod, "Reranker", _ExplodingReranker)
    with pytest.raises(WebResearchError) as excinfo:
        mod._rank("q", [_page("https://a.com/1", "A", markdown="body")], 5)

    assert seen == {"provider": "bge", "strict": True}
    assert "BGE rerank failed" in str(excinfo.value)
    assert "digisearch[rerank]" in str(excinfo.value)
    assert isinstance(excinfo.value.__cause__, RuntimeError)


def test_rank_skips_bm25_when_rank_bm25_missing(
    monkeypatch: pytest.MonkeyPatch, caplog: pytest.LogCaptureFixture
):
    from digisearch.chunking import factory as factory_mod
    from digisearch.search import keyword as keyword_mod
    from digisearch.search import reranker as reranker_mod
    from digisearch.web import answer as mod

    monkeypatch.setattr(factory_mod, "get_document_chunker", lambda: _FakeChunker())
    monkeypatch.setattr(keyword_mod, "_BM25_AVAILABLE", False)
    _fake_sentence_transformers(monkeypatch)
    seen: dict[str, Any] = {}
    monkeypatch.setattr(reranker_mod, "Reranker", _recording_reranker(seen))
    page = _page("https://a.com/1", "A", markdown="body")

    with caplog.at_level(logging.WARNING, logger="digisearch.web.answer"):
        cited = mod._rank("q", [page], 5)

    assert cited == [page]
    assert seen["provider"] == "bge"
    assert seen["strict"] is True
    assert seen["top_n"] == 5
    warnings = [record for record in caplog.records if "rank_bm25" in record.getMessage()]
    assert len(warnings) == 1


def test_rank_bm25_filter_keeps_positive_scores_caps_and_tags_chunks(monkeypatch):
    from digisearch.chunking import factory as factory_mod
    from digisearch.search import keyword as keyword_mod
    from digisearch.search import reranker as reranker_mod
    from digisearch.web import answer as mod

    monkeypatch.setattr(factory_mod, "get_document_chunker", lambda: _FakeChunker(chunks_per_doc=3))
    bm25_seen: dict[str, Any] = {}
    # candidates: corpus[2]=2.0, corpus[0]=1.5, corpus[1]=0.0 (zero-score dropped)
    monkeypatch.setattr(
        keyword_mod, "BM25Searcher", _fake_bm25([(2, 2.0), (0, 1.5), (1, 0.0)], bm25_seen)
    )
    _fake_sentence_transformers(monkeypatch)
    rerank_seen: dict[str, Any] = {}
    monkeypatch.setattr(reranker_mod, "Reranker", _recording_reranker(rerank_seen))
    page = _page("https://a.com/1", "A", markdown="body")

    cited = mod._rank("query text", [page], 2)

    assert bm25_seen["query"] == "query text"
    assert bm25_seen["top_k"] == 8  # cited_top_n * 4
    assert bm25_seen["corpus"] == [
        "chunk 0 of https://a.com/1",
        "chunk 1 of https://a.com/1",
        "chunk 2 of https://a.com/1",
    ]
    candidates = rerank_seen["candidates"]
    assert [c.chunk.content for c in candidates] == [
        "chunk 2 of https://a.com/1",
        "chunk 0 of https://a.com/1",
    ]  # zero-score chunk dropped
    assert candidates[0].chunk.metadata == {
        "source_url": "https://a.com/1",
        "title": "A",
        "evidence_tier": "External",
    }
    assert cited == [page]


def test_rank_dedupes_chunks_to_pages_in_rank_order(monkeypatch):
    from digisearch.chunking import factory as factory_mod
    from digisearch.search import keyword as keyword_mod
    from digisearch.search import reranker as reranker_mod
    from digisearch.web import answer as mod

    monkeypatch.setattr(factory_mod, "get_document_chunker", lambda: _FakeChunker(chunks_per_doc=2))
    # corpus: [A#0, A#1, B#0, B#1, C#0, C#1] -> candidates B#1, A#1, B#0
    monkeypatch.setattr(keyword_mod, "BM25Searcher", _fake_bm25([(3, 3.0), (1, 2.0), (2, 1.0)], {}))
    _fake_sentence_transformers(monkeypatch)
    rerank_seen: dict[str, Any] = {}
    monkeypatch.setattr(reranker_mod, "Reranker", _recording_reranker(rerank_seen))
    pages = [
        _page("https://a.com/1", "A"),
        _page("https://b.com/2", "B"),
        _page("https://c.com/3", "C"),
    ]

    cited = mod._rank("q", pages, 3)

    assert [p.url for p in cited] == [
        "https://b.com/2",
        "https://a.com/1",
    ]  # B, then A; C unsupported
    assert rerank_seen["top_n"] == 3


# ── _synthesize: digillm boundary + citation guard ────────────────────────────


def test_synthesize_requires_synthesis_model_env(monkeypatch):
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchConfig, WebResearchError

    monkeypatch.delenv("DIGISEARCH_SYNTHESIS_MODEL", raising=False)
    with pytest.raises(WebResearchError) as excinfo:
        mod._synthesize("q", [_page("https://a.com/1", "A")], WebResearchConfig())
    assert "DIGISEARCH_SYNTHESIS_MODEL" in str(excinfo.value)


def test_synthesize_calls_digillm_with_numbered_sources(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchConfig

    calls: dict[str, Any] = {}

    def fake_completion(model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        calls["model"] = model
        calls["messages"] = messages
        calls["kwargs"] = kwargs
        return _completion("Wafer raised $40M [1].")

    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", fake_completion)
    pages = [
        _page("https://a.com/1", "A", markdown="Wafer raised $40M."),
        _page("https://b.com/2", "B", markdown="A competitor hired."),
    ]

    text, counts = mod._synthesize("Series A?", pages, WebResearchConfig())

    assert text == "Wafer raised $40M [1]."
    assert counts == {"llm_calls": 1}
    assert calls["model"] == "openai/gpt-4o-mini"
    assert calls["kwargs"] == {"usage_kind": "web_search"}
    system = calls["messages"][0]["content"]
    user = calls["messages"][1]["content"]
    assert calls["messages"][0]["role"] == "system"
    assert calls["messages"][1]["role"] == "user"
    assert "ONLY" in system  # answer only from the numbered sources
    assert "insufficient sources" in system  # exact refusal wording taught to the model
    assert "[1] https://a.com/1" in user and "[2] https://b.com/2" in user
    assert "Series A?" in user


def test_synthesize_caps_snippet_and_total_source_chars(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchConfig

    calls: dict[str, Any] = {}

    def fake_completion(model: str, messages: list[dict[str, str]], **kwargs: Any) -> Any:
        calls["messages"] = messages
        return _completion("ok [1]")

    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", fake_completion)
    pages = [
        _page("https://a.com/1", "A", markdown="y" * 3000),
        _page("https://b.com/2", "B", markdown="z" * 3000),
    ]

    mod._synthesize("q", pages, WebResearchConfig(max_synthesis_chars=2500))

    user = calls["messages"][1]["content"]
    assert "y" * 2000 in user  # per-source snippet cap
    assert "y" * 2001 not in user
    assert user.count("y") + user.count("z") <= 2500  # total source budget


@pytest.mark.parametrize(
    ("answer", "expected_first_line"),
    [
        ("Answer [2].", "insufficient sources"),  # [2] never rendered under the budget
        ("Answer [1].", "Answer [1]."),
    ],
)
def test_synthesize_citation_guard_counts_only_rendered_sources(
    monkeypatch, answer, expected_first_line
):
    import digillm.client as digillm_client
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchConfig

    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _completion(answer))
    pages = [
        _page("https://a.com/1", "A", markdown="x" * 3000),
        _page("https://b.com/2", "B", markdown="y" * 3000),
    ]

    text, _ = mod._synthesize("q", pages, WebResearchConfig(max_synthesis_chars=1500))

    assert text.splitlines()[0] == expected_first_line
    if expected_first_line == "insufficient sources":
        assert "https://b.com/2" not in text  # omitted source is not listed either


@pytest.mark.parametrize("answer", ["I cannot answer that.", "Answer [0].", "Answer [9]."])
def test_synthesize_replaces_uncited_answer_with_insufficient_sentence(monkeypatch, answer):
    import digillm.client as digillm_client
    from digisearch.web import answer as mod
    from digisearch.web.grounding_models import WebResearchConfig

    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _completion(answer))
    pages = [_page("https://a.com/1", "A"), _page("https://b.com/2", "B")]

    text, counts = mod._synthesize("q", pages, WebResearchConfig())

    assert text.splitlines()[0] == "insufficient sources"
    assert "[1] https://a.com/1" in text and "[2] https://b.com/2" in text
    assert counts == {"llm_calls": 1}


def test_grounded_answer_insufficient_path_keeps_cited_sources(monkeypatch):
    import digillm.client as digillm_client
    from digisearch.web import answer as mod

    monkeypatch.setattr(mod, "_live", lambda q, top_n: [_hit("https://a.com/1", "A", score=0.9)])
    monkeypatch.setattr(mod, "_fetch", lambda h, top_n: [_page("https://a.com/1", "A")])
    monkeypatch.setattr(mod, "_rank", lambda q, p, top_n: p)
    monkeypatch.setenv("DIGISEARCH_SYNTHESIS_MODEL", "openai/gpt-4o-mini")
    monkeypatch.setattr(digillm_client, "completion", lambda *a, **k: _completion("No idea."))

    data, usage = mod.grounded_answer("q")

    assert data.output is not None
    assert data.output["text"].startswith("insufficient sources")
    assert data.results[0]["url"] == "https://a.com/1"  # still cited, still WebSearchData
    assert usage.llm_calls == 1


# ── module discipline pins ────────────────────────────────────────────────────


def test_answer_module_never_indexes():
    import ast
    import inspect

    from digisearch.web import answer as mod

    identifiers: set[str] = set()
    for node in ast.walk(ast.parse(inspect.getsource(mod))):
        if isinstance(node, ast.Name):
            identifiers.add(node.id)
        elif isinstance(node, ast.Attribute):
            identifiers.add(node.attr)
        elif isinstance(node, ast.alias):
            identifiers.add(node.name.rsplit(".", 1)[-1])
    assert "ingest_url" not in identifiers  # it indexes (R3)
    assert "ingest_source" not in identifiers


def test_answer_module_scope_keeps_optional_deps_lazy():
    import ast
    import inspect

    from digisearch.web import answer as mod

    tree = ast.parse(inspect.getsource(mod))
    module_imports: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Import):
            module_imports.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            module_imports.add(node.module)
    forbidden = (
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
