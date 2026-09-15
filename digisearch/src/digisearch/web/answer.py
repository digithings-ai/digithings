"""Phase B grounded answer synthesis (#4064) — the Perplexica-style loop.

Live search → fetch → chunk → BM25 filter → BGE rerank → digillm synthesis
with inline ``[n]`` citations. Retrieval rows stay the landed
``WebSearchResult``; the returned envelope is the landed
``web_exa.WebSearchData`` (R1). Fetched pages are never indexed: this module
stays off the pipeline URL-ingest path (R3).

Fail-hard: any dependency failure — or zero cited pages — raises
``WebResearchError``; the cited set is never arbitrary. The landed
``Reranker._rerank_bge`` falls back to the original order on any exception,
so ``_rank`` opens its BGE stage with an explicit ``importlib.util.find_spec``
pre-guard — that fail-open fallback is unreachable from this path.
``rank_bm25`` is the one optional filter: absent, BM25 filtering is skipped
and the rerank still runs.
"""

# score:allow untyped any
# digillm chat payloads and parsed model replies are dynamic JSON; Any is the honest annotation.

from __future__ import annotations

import importlib.util
import logging
import os
import re
import time
from typing import TYPE_CHECKING, Any

from digisearch.core.models import Document, Query, Result
from digisearch.web.accounting import estimate_cost, finalize_usage, record_stage, start_clock
from digisearch.web.grounding_models import (
    EFFORT_PRESETS,
    EffortMode,
    TurnUsage,
    WebResearchConfig,
    WebResearchError,
)
from digisearch.web.retrieve import FetchedPage, fetch_pages, live_search
from digisearch.web_exa import WebSearchData

if TYPE_CHECKING:
    from digisearch.web_search.models import WebSearchResult

__all__ = ["grounded_answer"]

logger = logging.getLogger(__name__)

#: digillm model id for grounded synthesis, resolved at call time.
SYNTHESIS_MODEL_ENV = "DIGISEARCH_SYNTHESIS_MODEL"

#: Literal answer text when the cited set cannot support one (M8 trigger split).
INSUFFICIENT_SOURCES = "insufficient sources"

#: Per-source prompt snippet budget; the whole source block stays within
#: ``WebResearchConfig.max_synthesis_chars``.
_SNIPPET_CHARS = 2000

_CITATION_RE = re.compile(r"\[(\d+)\]")

_SYSTEM_PROMPT = (
    "You answer the user's question from numbered web sources.\n"
    "Rules:\n"
    "1. Answer ONLY from the numbered sources.\n"
    "2. End every factual claim with its source number in square brackets, like [1].\n"
    "3. Never state a fact that no numbered source supports.\n"
    f"4. If the numbered sources cannot answer the question, reply with exactly: "
    f"{INSUFFICIENT_SOURCES}"
)


def _live(query: str, top_n: int) -> list[WebSearchResult]:
    """Task 1 search seam — delegates to ``retrieve.live_search``."""
    return live_search(query, top_n=top_n)


def _fetch(hits: list[WebSearchResult], top_n: int) -> list[FetchedPage]:
    """Task 1 fetch seam — delegates to ``retrieve.fetch_pages`` (never indexes)."""
    return fetch_pages(hits, top_n=top_n)


def _chunk_pages(pages: list[FetchedPage], chunker: Any) -> list[Result]:
    """One ``Result`` per chunk, each chunk tagged with its source metadata."""
    results: list[Result] = []
    for page in pages:
        doc = Document(id=page.url, content=page.markdown, source=page.url, doc_type="web")
        try:
            chunks = chunker.chunk(doc)
        except Exception as exc:
            raise WebResearchError(f"web page chunking failed for {page.url}: {exc}") from exc
        for chunk in chunks:
            chunk.metadata = {
                **chunk.metadata,
                "source_url": page.url,
                "title": page.title,
                "evidence_tier": "External",
            }
            results.append(Result(chunk=chunk, score=0.0))
    return results


def _bm25_filter(question: str, results: list[Result], top_n: int) -> list[Result]:
    """Keep BM25-positive chunks (cap ``top_n * 4``); missing rank_bm25 skips this.

    The landed ``BM25Searcher`` keys its hits by corpus index
    (``Chunk.id = str(index)``), which is how the originals are recovered.
    """
    try:
        from digisearch.search.keyword import BM25Searcher

        searcher = BM25Searcher([result.chunk.content for result in results])
        hits = searcher.search(Query(text=question), top_k=top_n * 4)
    except ImportError:
        logger.warning(
            "rank_bm25 is not installed; skipping the BM25 filter and reranking every chunk",
            extra={"operation": "web_rank", "outcome": "bm25_unavailable"},
        )
        return results
    kept: list[Result] = []
    for hit in hits[: top_n * 4]:
        if hit.score <= 0:
            continue
        try:
            kept.append(results[int(hit.chunk.id)])
        except (TypeError, ValueError, IndexError):
            continue
    return kept


def _rank(question: str, pages: list[FetchedPage], top_n: int) -> list[FetchedPage]:
    """Chunk → BM25 (optional) → BGE rerank; cited pages in rank order.

    The BGE stage opens with an explicit pre-import guard: the landed
    ``Reranker._rerank_bge`` swallows every exception and falls back to the
    original order, so a missing ``sentence-transformers`` must fail here,
    before ``Reranker`` is touched.
    """
    try:
        from digisearch.chunking.factory import get_document_chunker

        chunker = get_document_chunker()
    except Exception as exc:
        raise WebResearchError(f"web chunking is unavailable: {exc}") from exc

    results = _chunk_pages(pages, chunker)
    if not results:
        return []
    candidates = _bm25_filter(question, results, top_n)

    if importlib.util.find_spec("sentence_transformers") is None:
        raise WebResearchError(
            "BGE rerank requires the 'rerank' extra (sentence-transformers): "
            "install digisearch[rerank]; refusing to return an unranked cited set"
        )
    from digisearch.search.reranker import Reranker

    try:
        reranked = Reranker(provider="bge", strict=True).rerank(question, candidates, top_n=top_n)
    except Exception as exc:
        raise WebResearchError(
            f"BGE rerank failed ({exc}); install or repair digisearch[rerank] — "
            "refusing to return an unranked cited set"
        ) from exc

    by_url = {page.url: page for page in pages}
    cited: list[FetchedPage] = []
    seen: set[str] = set()
    for hit in reranked:
        url = str(hit.chunk.metadata.get("source_url") or "")
        page = by_url.get(url)
        if page is not None and url not in seen:
            seen.add(url)
            cited.append(page)
    return cited


def _source_line(index: int, page: FetchedPage) -> str:
    label = f"[{index}] {page.url}"
    return f"{label} — {page.title}" if page.title else label


def _numbered_sources(pages: list[FetchedPage], max_chars: int) -> tuple[str, int]:
    """Numbered sources with per-source and total snippet budgets.

    Returns the rendered text and how many sources actually rendered — sources
    dropped once the budget is exhausted are not citable.
    """
    blocks: list[str] = []
    used = 0
    for index, page in enumerate(pages, 1):
        remaining = max_chars - used
        if remaining <= 0:
            break
        snippet = page.markdown[:_SNIPPET_CHARS]
        if len(snippet) > remaining:
            snippet = snippet[:remaining]
        used += len(snippet)
        blocks.append(f"{_source_line(index, page)}\n{snippet}")
    return "SOURCES:\n" + "\n\n".join(blocks), len(blocks)


def _insufficient_text(pages: list[FetchedPage]) -> str:
    """The literal insufficient-sources sentence plus the numbered source list."""
    listing = "\n".join(_source_line(index, page) for index, page in enumerate(pages, 1))
    return f"{INSUFFICIENT_SOURCES}\n\n{listing}"


def _is_cited(answer: str, source_count: int) -> bool:
    return any(1 <= int(match) <= source_count for match in _CITATION_RE.findall(answer))


def _message_text(response: Any) -> str:
    try:
        content = response.choices[0].message.content
    except (AttributeError, IndexError, TypeError) as exc:
        raise WebResearchError(f"web synthesis returned an unusable response: {exc}") from exc
    return str(content or "").strip()


def _synthesize(
    question: str, pages: list[FetchedPage], cfg: WebResearchConfig
) -> tuple[str, dict[str, int]]:
    """Grounded synthesis over the cited pages; never returns an uncited answer."""
    model = os.environ.get(SYNTHESIS_MODEL_ENV, "").strip()
    if not model:
        raise WebResearchError(
            f"{SYNTHESIS_MODEL_ENV} is not set — no model for grounded web synthesis. "
            f"Set {SYNTHESIS_MODEL_ENV} to the digillm model id."
        )
    try:
        from digillm.client import completion
    except ImportError as exc:
        raise WebResearchError(
            "grounded web synthesis requires the digillm client, which is not importable"
        ) from exc

    sources, rendered = _numbered_sources(pages, cfg.max_synthesis_chars)
    messages = [
        {"role": "system", "content": _SYSTEM_PROMPT},
        {"role": "user", "content": f"{sources}\n\nQuestion: {question}"},
    ]
    try:
        response = completion(model, messages, usage_kind="web_search")
    except Exception as exc:
        raise WebResearchError(f"web synthesis failed: {exc}") from exc

    answer = _message_text(response)
    if not _is_cited(answer, rendered):
        logger.warning(
            "synthesis returned no valid [n] citation; answering with the literal "
            "insufficient-sources sentence plus the source list",
            extra={"operation": "web_synthesize", "outcome": "insufficient_sources"},
        )
        answer = _insufficient_text(pages[:rendered])
    return answer, {"llm_calls": 1}


def grounded_answer(
    question: str, *, config: WebResearchConfig | None = None
) -> tuple[WebSearchData, TurnUsage]:
    """Run the web research loop and return the envelope plus per-turn usage.

    Raises :class:`WebResearchError` on any dependency failure or when no
    source survives to cite. Usage travels as the explicit second tuple
    element — ``WebSearchData`` is ``extra="ignore"`` and drops extras.
    """
    cfg = config or EFFORT_PRESETS[EffortMode.FAST]
    timer = start_clock()

    started = time.perf_counter()
    hits = _live(question, cfg.live_top_n)
    record_stage(timer, "search_ms", int((time.perf_counter() - started) * 1000))

    started = time.perf_counter()
    pages = _fetch(hits, cfg.fetch_top_n)
    record_stage(timer, "fetch_ms", int((time.perf_counter() - started) * 1000))

    started = time.perf_counter()
    cited = _rank(question, pages, cfg.cited_top_n)
    record_stage(timer, "rerank_ms", int((time.perf_counter() - started) * 1000))
    if not cited:
        raise WebResearchError(
            f"web research found no citable sources for {question!r} "
            f"({len(pages)} fetched page(s) survived filtering)"
        )

    started = time.perf_counter()
    answer, counts = _synthesize(question, cited, cfg)
    record_stage(timer, "synthesis_ms", int((time.perf_counter() - started) * 1000))

    llm_calls = int(counts.get("llm_calls", 0))
    usage = finalize_usage(
        timer,
        searches=1,
        pages_fetched=len(pages),
        pages_cited=len(cited),
        llm_calls=llm_calls,
    )

    hits_by_url = {hit.url: hit for hit in hits}
    results: list[dict[str, Any]] = []
    for page in cited:
        hit = hits_by_url.get(page.url)
        results.append(
            {
                "title": page.title,
                "url": page.url,
                "snippet": page.markdown[:_SNIPPET_CHARS],
                "score": float(hit.score) if hit is not None else 0.0,
                "engine": hit.engine if hit is not None else "",
            }
        )
    data = WebSearchData(
        results=results,
        output={"text": answer},
        search_type=f"web-{cfg.effort.value}",
        cost_dollars=estimate_cost(
            searches=1, pages_fetched=len(pages), llm_calls=llm_calls
        ).model_dump(),
    )
    return data, usage
