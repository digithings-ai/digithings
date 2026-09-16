"""Web branch nodes for the research turn (#4064): plan → web_retrieve → web_aggregate.

Retrieval reuses the Task 3 seams (``_live`` / ``_fetch`` / ``_rank``) and
synthesis reuses the landed Task 3/4 monoliths; this module only wires them,
maps web hits onto the corpus citation shape, and rebuilds the turn's
results/usage/cost from the hits this branch actually retrieved. Exactly one
search/fetch/rank round runs per turn (#4084): ``web_retrieve`` stores the
cited pages as ``web_pages`` and ``web_aggregate`` feeds them back through the
monoliths' ``pages=`` seam, so synthesis never retrieves again. Fail-hard:
any :class:`WebResearchError` becomes ``state.error`` plus a failed trace step,
never a citation-free answer.
"""

# score:allow untyped any
# Web-branch state and trace payloads are heterogeneous JSON; Any is the honest annotation.

from __future__ import annotations

import logging
import time
from typing import Any

from pydantic import ValidationError

from digisearch.agent.citations import rag_sources_from_hits
from digisearch.agent.pipeline_models import ResearchTurnState, ResearchTurnTraceStep
from digisearch.web.accounting import estimate_cost, finalize_usage, record_stage, start_clock
from digisearch.web.answer import _SNIPPET_CHARS, _fetch, _live, _rank, grounded_answer
from digisearch.web.grounding_models import (
    EFFORT_PRESETS,
    EffortMode,
    TurnUsage,
    WebResearchConfig,
    WebResearchError,
)
from digisearch.web.retrieve import FetchedPage
from digisearch.web.structured import structured_synthesis
from digisearch.web_search.models import WebSearchResult

logger = logging.getLogger(__name__)

__all__ = [
    "WEB_BACKEND",
    "node_web_aggregate",
    "node_web_retrieve",
    "resolve_web_config",
    "run_web_research_turn",
]

#: Turn ``backend`` label for the OSS web branch.
WEB_BACKEND = "web-oss"


def resolve_web_config(*, effort: str, cited_top_n: int | None) -> WebResearchConfig:
    """Resolve the effort preset; an explicit request ``cited_top_n`` wins (R9)."""
    try:
        mode = EffortMode(str(effort or "").strip().lower())
    except ValueError as exc:
        raise WebResearchError(
            f"invalid effort: {effort!r} (expected 'fast' or 'thorough')"
        ) from exc
    preset = EFFORT_PRESETS[mode]
    if cited_top_n is None:
        return preset.model_copy()
    return preset.model_copy(update={"cited_top_n": int(cited_top_n)})


def _web_step_failure(step: str, detail: str) -> dict[str, Any]:
    """Failed web-branch step mirroring the corpus retrieve-failure shape."""
    return {
        "error": detail,
        "trace": [
            ResearchTurnTraceStep(step=step, status="failed", service="digisearch", detail=detail)
        ],
    }


def _normalized_hit(page: FetchedPage, hit: WebSearchResult | None) -> dict[str, Any]:
    """One cited page as the landed ``{url,title,snippet,score,engine}`` hit shape."""
    return {
        "url": page.url,
        "title": page.title,
        "snippet": page.markdown[:_SNIPPET_CHARS],
        "score": float(hit.score) if hit is not None else 0.0,
        "engine": hit.engine if hit is not None else "",
    }


def _web_result_row(hit: dict[str, Any]) -> dict[str, Any]:
    """One turn result row: the normalized web hit plus the External evidence tier."""
    return {
        "url": str(hit.get("url") or ""),
        "title": str(hit.get("title") or ""),
        "snippet": str(hit.get("snippet") or ""),
        "score": hit.get("score"),
        "engine": str(hit.get("engine") or ""),
        "metadata": {"evidence_tier": "External"},
    }


def _web_hit_to_rag_row(hit: dict[str, Any], rank: int) -> dict[str, Any]:
    """Map a web hit to the corpus citation row ``rag_sources_from_hits`` reads.

    Raw web hits carry ``url``/``snippet``; the citation builder reads
    ``doc_id``/``content``/``chunk_id``, so routing them straight in would yield
    citation-free entries with no URL.
    """
    url = str(hit.get("url") or "")
    return {
        "doc_id": url,
        "content": str(hit.get("snippet") or ""),
        "score": hit.get("score"),
        "rank": rank,
        "metadata": {
            "source_url": url,
            "title": str(hit.get("title") or ""),
            "engine": str(hit.get("engine") or ""),
            "evidence_tier": "External",
        },
    }


def _formatted_line(rank: int, hit: dict[str, Any]) -> str:
    """One ``[n] url — title — snippet`` context line (never ``format_web_results``)."""
    parts = [str(hit.get("url") or "")]
    title = str(hit.get("title") or "").strip()
    if title:
        parts.append(title)
    snippet = str(hit.get("snippet") or "").strip()
    if snippet:
        parts.append(snippet)
    return f"[{rank}] " + " — ".join(parts)


def node_web_retrieve(state: ResearchTurnState) -> dict[str, Any]:
    """Search/fetch/rank the live web; store cited hits + pages plus retrieval usage."""
    if state.error:
        return {}
    question = str(state.user_message).strip()
    try:
        cfg = resolve_web_config(effort=state.effort, cited_top_n=state.cited_top_n)
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
    except WebResearchError as exc:
        logger.debug("web_retrieve failed: %s", exc)
        return _web_step_failure("web_retrieve", str(exc))
    hits_by_url = {hit.url: hit for hit in hits}
    web_hits = [_normalized_hit(page, hits_by_url.get(page.url)) for page in cited]
    usage = finalize_usage(timer, searches=1, pages_fetched=len(pages), pages_cited=len(cited))
    return {
        "web_hits": web_hits,
        "web_pages": [page.model_dump(mode="json") for page in cited],
        "usage": usage.model_dump(mode="json"),
        "trace": [
            ResearchTurnTraceStep(
                step="web_retrieve",
                status="ok",
                service="digisearch",
                total=len(cited),
                detail=", ".join(page.url for page in cited),
            )
        ],
    }


def _cited_pages_from_state(state: ResearchTurnState) -> list[FetchedPage]:
    """Rebuild the retrieve node's cited pages from their JSON dumps.

    ``web_pages`` is untyped JSON on the turn state, so a corrupt or drifted
    dump fails hard here as :class:`WebResearchError` instead of leaking
    ``pydantic.ValidationError`` past the node's fail-hard funnel.
    """
    try:
        return [FetchedPage.model_validate(page) for page in state.web_pages or []]
    except ValidationError as exc:
        raise WebResearchError(f"web_pages in turn state failed validation: {exc}") from exc


def node_web_aggregate(state: ResearchTurnState) -> dict[str, Any]:
    """Synthesize from the retrieved pages, then rebuild results/citations/accounting.

    The cited pages come from ``state.web_pages`` (written by
    :func:`node_web_retrieve`) and are passed to the synthesis monoliths
    through their ``pages=`` seam — no second search/fetch/rank round.
    """
    if state.error:
        return {}
    question = str(state.user_message).strip()
    try:
        cfg = resolve_web_config(effort=state.effort, cited_top_n=state.cited_top_n)
        cited_pages = _cited_pages_from_state(state)
        if state.output_schema:
            data, synthesis = structured_synthesis(
                question, output_schema=state.output_schema, config=cfg, pages=cited_pages
            )
        else:
            data, synthesis = grounded_answer(question, config=cfg, pages=cited_pages)
    except WebResearchError as exc:
        logger.debug("web_aggregate failed: %s", exc)
        return _web_step_failure("web_aggregate", str(exc))

    web_hits = [hit for hit in (state.web_hits or []) if isinstance(hit, dict)]
    retrieval = TurnUsage.model_validate(state.usage or {})
    timer = start_clock()
    record_stage(timer, "search_ms", retrieval.search_ms)
    record_stage(timer, "fetch_ms", retrieval.fetch_ms)
    record_stage(timer, "rerank_ms", retrieval.rerank_ms)
    record_stage(timer, "synthesis_ms", synthesis.synthesis_ms)
    usage = finalize_usage(
        timer,
        searches=retrieval.searches or 1,
        pages_fetched=retrieval.pages_fetched,
        pages_cited=len(web_hits),
        llm_calls=synthesis.llm_calls,
    )
    rag_rows = [_web_hit_to_rag_row(hit, rank) for rank, hit in enumerate(web_hits, start=1)]
    return {
        "backend": WEB_BACKEND,
        "results": [_web_result_row(hit) for hit in web_hits],
        "rag_sources": rag_sources_from_hits(rag_rows),
        "formatted_context": "\n".join(
            _formatted_line(rank, hit) for rank, hit in enumerate(web_hits, start=1)
        ),
        "web_output": dict(data.output or {}),
        "cost_dollars": estimate_cost(
            searches=usage.searches,
            pages_fetched=usage.pages_fetched,
            llm_calls=usage.llm_calls,
        ).model_dump(mode="json"),
        "usage": usage.model_dump(mode="json"),
        "trace": [
            ResearchTurnTraceStep(
                step="web_aggregate", status="ok", service="digisearch", total=len(web_hits)
            )
        ],
    }


def run_web_research_turn(initial: dict[str, Any]) -> dict[str, Any]:
    """Run one research turn through the web branch (defaults ``source`` to ``web``)."""
    from digisearch.agent.pipeline import run_research_turn

    payload = dict(initial)
    if str(payload.get("source") or "").strip().lower() not in {"web", "auto"}:
        payload["source"] = "web"
    out = run_research_turn(payload)
    if out.get("error") is None:
        out["backend"] = WEB_BACKEND
    return out
