"""SearXNG sidecar provider (primary) for #3853."""

from __future__ import annotations

import logging

import httpx

from digisearch.web_search.models import (
    WebSearchRequest,
    WebSearchResponse,
    WebSearchResult,
    apply_domain_filter,
    recency_days_to_searxng_time_range,
)

logger = logging.getLogger(__name__)


def _normalize_unresponsive_engines(raw: object) -> list[str]:
    """Coerce searxng's ``unresponsive_engines`` into ``"<engine>: <reason>"`` rows.

    searxng reports blocked/timed-out engines as a list of ``[engine, reason]``
    pairs, e.g. ``[["duckduckgo", "access denied"], ["wikidata", "timeout"]]``
    (#4297). The field can be missing, not a list, or hold malformed entries, so
    coerce best-effort instead of raising: this is diagnostic metadata riding an
    already-successful response, and a malformed shape must never fail a search.
    """
    if not isinstance(raw, list):
        return []
    out: list[str] = []
    for item in raw:
        if isinstance(item, (list, tuple)):
            name = str(item[0]) if item else ""
            reason = str(item[1]) if len(item) > 1 else ""
            if name and reason:
                out.append(f"{name}: {reason}")
            elif name:
                out.append(name)
            elif item:
                out.append(str(item))
        elif item:
            out.append(str(item))
    return out


class SearXNGWebSearchProvider:
    name = "searxng"

    def __init__(
        self,
        base_url: str = "http://127.0.0.1:8080",
        client: httpx.Client | None = None,
        timeout: float = 15.0,
    ) -> None:
        self._base = base_url.rstrip("/")
        self._client = client
        self._timeout = timeout

    def search(self, req: WebSearchRequest) -> WebSearchResponse:
        params: dict[str, object] = {
            "q": req.query,
            "format": "json",
            "pageno": 1,
            "language": "en",
            "safesearch": 1,
        }
        time_range = recency_days_to_searxng_time_range(req.recency_days)
        if time_range is not None:
            params["time_range"] = time_range
        close = False
        client = self._client
        if client is None:
            client = httpx.Client(timeout=self._timeout)
            close = True
        unresponsive: list[str] = []
        try:
            r = client.get(f"{self._base}/search", params=params)
            r.raise_for_status()
            payload = r.json()
            items = (payload.get("results", []) or [])[: req.max_results * 2]
            unresponsive = _normalize_unresponsive_engines(payload.get("unresponsive_engines"))
        finally:
            if close:
                client.close()
        rows = [
            {
                "url": str(it.get("url", "")),
                "title": str(it.get("title", "")),
                "snippet": str(it.get("content", "")),
                "score": float(it.get("score", 0.0) or 0.0),
                "engine": str(it.get("engine", "")),
            }
            for it in items
        ]
        rows = apply_domain_filter(
            rows, include_domains=req.include_domains, exclude_domains=req.exclude_domains
        )
        rows = sorted(rows, key=lambda d: float(d.get("score", 0.0) or 0.0), reverse=True)
        results = [
            WebSearchResult(
                url=d["url"],
                title=d["title"],
                snippet=d["snippet"],
                score=float(d.get("score", 0.0) or 0.0),
                engine=str(d.get("engine", "searxng")),
            )
            for d in rows[: req.max_results]
            if d["url"]
        ]
        # Diagnostics only (#4297): never changes which provider wins nor turns a
        # successful empty response into an error. An empty result body used to
        # be completely silent, so the hosted container — whose only
        # observability channel is this HTTP response — could not tell which
        # engines were blocked. Log every non-empty unresponsive list, and every
        # successful-but-empty response, at WARNING.
        if unresponsive:
            logger.warning(
                "searxng returned %d result(s) with unresponsive engines: %s",
                len(results),
                "; ".join(unresponsive),
            )
        elif not results:
            logger.warning("searxng returned a successful empty response (0 results)")
        provider = self.name
        if not results and unresponsive:
            # Additive client-visible diagnostic: keep the response shape
            # ({query, results, provider}) unchanged and name the failing
            # engines in the already-serialized provider field only when the
            # response is empty. Non-empty responses, and empty responses with
            # no unresponsive list, keep the bare provider name.
            compact = ",".join(engine.replace(": ", ":") for engine in unresponsive)
            provider = f"{self.name}(none; unresponsive={compact})"
        return WebSearchResponse(query=req.query, results=results, provider=provider)
