"""Optional EXA web-search provider for digisearch (thin wrapper, dormant by default).

EXA (https://exa.ai) is a neural web-search API used by OpenCode's ``websearch``
tool. This module exposes it as an *alternative* retrieval path alongside the
owned-corpus backends (Chroma / Azure / Vectorize): live web search, page
contents, grounded answers, and find-similar — including deep-research types
(``deep``, ``deep-reasoning``), structured outputs (``output_schema``), and
freshness controls (``livecrawl`` / ``max_age_hours``).

Design constraints (see ``digisearch/AGENTS.md``):

- No new hard dependencies: transport is ``httpx`` (already in base install).
  No ``exa-py`` import; the REST shapes are built locally.
- No env reads at import time: ``is_exa_configured()`` / ``_api_key()`` read
  ``EXA_API_KEY`` at call time so tests and key-less installs stay side-effect
  free. Without a key every entry point fails closed with
  :class:`ExaNotConfiguredError` / a plain disabled string for MCP.
- No silent corpus mixing: results are EXA-native dicts (title/url/highlights),
  never merged into ``SearchResponse``. Callers choose explicitly.
"""

from __future__ import annotations

import logging
import os
from typing import Any, Literal

import httpx
from pydantic import BaseModel, Field

logger = logging.getLogger(__name__)

EXA_API_BASE = "https://api.exa.ai"
EXA_ENV_VAR = "EXA_API_KEY"
EXA_TIMEOUT_S = 30.0

#: Upstream ``numResults`` cap for ``POST /search``. EXA has no offset
#: parameter, so paging is a client-side slice of one enlarged window and this
#: is the hard ceiling for that window. Pinned in-repo by the monitors model's
#: 1-100 bound (``digisearch.monitors.models.Watch.num_results``, R6) asserted
#: in ``tests/ds/test_monitors_models.py::test_num_results_bounds_are_exa_cap``
#: and mirrored by the orchestrator manifest's "1-100" description; the #4123
#: live-pin reconciliation did not move it.
EXA_MAX_RESULTS = 100

ExaSearchType = Literal["instant", "fast", "auto", "deep-lite", "deep", "deep-reasoning"]

VALID_SEARCH_TYPES: frozenset[str] = frozenset(
    {"instant", "fast", "auto", "deep-lite", "deep", "deep-reasoning"}
)


class ExaNotConfiguredError(RuntimeError):
    """Raised when EXA is called without ``EXA_API_KEY`` set."""


class ExaError(RuntimeError):
    """Raised on EXA transport / API errors (status, payload)."""


class ExaPageOutOfRangeError(ValueError):
    """Raised when a paging window reaches past :data:`EXA_MAX_RESULTS`.

    A ``ValueError`` subclass so every existing ``except ValueError`` call site
    keeps handling callers' out-of-range requests as invalid input.
    """


class WebSearchData(BaseModel):
    """Orchestrator payload for a ``digisearch_web_search`` invoke."""

    model_config = {"extra": "ignore"}

    results: list[dict[str, Any]] = Field(default_factory=list)
    output: dict[str, Any] | None = None
    search_type: str | None = None
    cost_dollars: dict[str, Any] | None = None


def is_exa_configured() -> bool:
    """Return True when ``EXA_API_KEY`` is present (non-empty after strip)."""
    return bool(os.environ.get(EXA_ENV_VAR, "").strip())


def _api_key(explicit: str | None = None) -> str:
    key = (explicit or os.environ.get(EXA_ENV_VAR, "")).strip()
    if not key:
        raise ExaNotConfiguredError(
            f"{EXA_ENV_VAR} is not set — EXA web search is disabled. "
            f"Set {EXA_ENV_VAR} to enable digisearch_web_search."
        )
    return key


def _post(path: str, payload: dict[str, Any], *, api_key: str) -> dict[str, Any]:
    url = f"{EXA_API_BASE}{path}"
    try:
        resp = httpx.post(
            url,
            json=payload,
            headers={"x-api-key": api_key, "Content-Type": "application/json"},
            timeout=EXA_TIMEOUT_S,
        )
    except httpx.HTTPError as e:
        raise ExaError(f"EXA request failed: {e}") from e
    if resp.status_code in (401, 403):
        raise ExaError("EXA rejected the API key (401/403) — check EXA_API_KEY.")
    if resp.status_code == 429:
        raise ExaError("EXA rate limited this key (429) — back off and retry.")
    if resp.status_code >= 400:
        raise ExaError(f"EXA {path} failed ({resp.status_code}): {resp.text[:500]}")
    try:
        data = resp.json()
    except ValueError as e:
        raise ExaError(f"EXA {path} returned non-JSON") from e
    if not isinstance(data, dict):
        raise ExaError(f"EXA {path} returned unexpected shape")
    return data


def exa_search(
    query: str,
    *,
    search_type: ExaSearchType = "auto",
    num_results: int = 8,
    offset: int = 0,
    category: str | None = None,
    contents_highlights: bool = True,
    contents_text: bool = False,
    contents_summary: bool = False,
    max_characters: int = 4000,
    livecrawl: Literal["fallback", "preferred"] | None = None,
    max_age_hours: int | None = None,
    include_domains: list[str] | None = None,
    exclude_domains: list[str] | None = None,
    start_published_date: str | None = None,
    end_published_date: str | None = None,
    output_schema: dict[str, Any] | None = None,
    system_prompt: str | None = None,
    api_key: str | None = None,
) -> WebSearchData:
    """Run ``POST /search`` against EXA and return native results + synthesis.

    Paging: EXA has no offset parameter and caps ``numResults`` upstream
    (:data:`EXA_MAX_RESULTS`, currently 100), so ``offset`` selects the
    client-side slice ``results[offset : offset + num_results]`` of one enlarged
    window fetched with ``numResults = offset + num_results``. ``offset=0`` is
    the unpaged call. A window reaching past the cap — ``offset + num_results >
    EXA_MAX_RESULTS``, including ``offset >= EXA_MAX_RESULTS`` — raises
    :class:`ExaPageOutOfRangeError` before any request: pages beyond the cap are
    unreachable and are never silently truncated.
    """
    q = (query or "").strip()
    if not q:
        raise ValueError("query is required")
    if search_type not in VALID_SEARCH_TYPES:
        raise ValueError(f"invalid search_type: {search_type!r}")
    n = max(1, min(int(num_results), EXA_MAX_RESULTS))
    start = int(offset)
    if start < 0:
        raise ValueError("offset must be >= 0")
    if start + n > EXA_MAX_RESULTS:
        raise ExaPageOutOfRangeError(
            f"requested window [{start}, {start + n}) exceeds the EXA numResults cap "
            f"({EXA_MAX_RESULTS}); results past the cap are unreachable — lower num_results "
            f"or start at an earlier offset"
        )
    key = _api_key(api_key)
    contents: dict[str, Any] = {}
    if contents_highlights:
        contents["highlights"] = {"query": q, "maxCharacters": max(1, min(max_characters, 10000))}
    if contents_text:
        contents["text"] = True
    if contents_summary:
        contents["summary"] = True
    if max_age_hours is not None:
        contents["maxAgeHours"] = int(max_age_hours)
    if livecrawl == "preferred" and "maxAgeHours" not in contents:
        contents["maxAgeHours"] = 0
    payload: dict[str, Any] = {"query": q, "type": search_type, "numResults": start + n}
    if category:
        payload["category"] = category
    if contents:
        payload["contents"] = contents
    if include_domains:
        payload["includeDomains"] = include_domains
    if exclude_domains:
        payload["excludeDomains"] = exclude_domains
    if start_published_date:
        payload["startPublishedDate"] = start_published_date
    if end_published_date:
        payload["endPublishedDate"] = end_published_date
    if output_schema is not None:
        payload["outputSchema"] = output_schema
    if system_prompt:
        payload["systemPrompt"] = system_prompt
    data = _post("/search", payload, api_key=key)
    results = data.get("results") if isinstance(data.get("results"), list) else []
    output = data.get("output") if isinstance(data.get("output"), dict) else None
    cost = data.get("costDollars") if isinstance(data.get("costDollars"), dict) else None
    # Slice after filtering non-dict rows so ``offset`` counts the results the
    # caller actually sees.
    window = [r for r in results if isinstance(r, dict)]
    return WebSearchData(
        results=window[start:],
        output=output,
        search_type=str(data.get("searchType") or data.get("resolvedSearchType") or search_type),
        cost_dollars=cost,
    )


def exa_contents(
    urls: list[str],
    *,
    text: bool = True,
    highlights: bool = False,
    summary: bool = False,
    highlight_query: str | None = None,
    max_characters: int = 4000,
    subpages: int = 0,
    max_age_hours: int | None = None,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run ``POST /contents`` for known URLs (mirrors EXA contents options)."""
    clean = [u.strip() for u in (urls or []) if u and u.strip()]
    if not clean:
        raise ValueError("urls is required (non-empty)")
    key = _api_key(api_key)
    payload: dict[str, Any] = {"urls": clean}
    if text:
        payload["text"] = True
    if highlights:
        payload["highlights"] = (
            {"query": highlight_query, "maxCharacters": max_characters} if highlight_query else True
        )
    if summary:
        payload["summary"] = True
    if subpages:
        payload["subpages"] = max(0, min(int(subpages), 20))
    if max_age_hours is not None:
        payload["maxAgeHours"] = int(max_age_hours)
    return _post("/contents", payload, api_key=key)


def exa_answer(
    question: str,
    *,
    api_key: str | None = None,
) -> dict[str, Any]:
    """Run ``POST /answer`` — grounded LLM answer with citations."""
    q = (question or "").strip()
    if not q:
        raise ValueError("question is required")
    return _post("/answer", {"query": q}, api_key=_api_key(api_key))


def exa_find_similar(
    url: str,
    *,
    num_results: int = 10,
    api_key: str | None = None,
) -> WebSearchData:
    """Run ``POST /findSimilar`` for competitor / related-page discovery."""
    u = (url or "").strip()
    if not u:
        raise ValueError("url is required")
    data = _post(
        "/findSimilar",
        {"url": u, "numResults": max(1, min(int(num_results), 100))},
        api_key=_api_key(api_key),
    )
    results = data.get("results") if isinstance(data.get("results"), list) else []
    return WebSearchData(results=[r for r in results if isinstance(r, dict)])


def format_web_results(data: WebSearchData, *, max_items: int = 10) -> str:
    """Render EXA results as compact text for MCP / chat consumption."""
    if not data.results:
        if data.output:
            return f"EXA answer:\n{data.output}"
        return "No EXA results found. Try a different query."
    lines: list[str] = []
    for r in data.results[: max(1, max_items)]:
        title = str(r.get("title") or "N/A")
        link = str(r.get("url") or "")
        published = str(r.get("publishedDate") or "N/A")
        author = str(r.get("author") or "N/A")
        lines.append(f"Title: {title}\nURL: {link}\nPublished: {published}\nAuthor: {author}")
        highlights = r.get("highlights")
        if isinstance(highlights, list) and highlights:
            joined = "\n".join(str(h) for h in highlights[:5])
            lines.append(f"Highlights:\n{joined}")
        elif r.get("text"):
            lines.append(f"Text: {str(r['text'])[:2000]}")
    if data.output:
        lines.append(f"Synthesized output:\n{data.output}")
    return "\n\n---\n\n".join(lines)
