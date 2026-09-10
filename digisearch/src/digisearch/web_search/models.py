"""Web-search Pydantic models for #3853."""

from __future__ import annotations

from urllib.parse import urlparse

from pydantic import BaseModel, Field


class WebSearchResult(BaseModel):
    url: str
    title: str = ""
    snippet: str = ""
    score: float = 0.0
    engine: str = ""


class WebSearchResponse(BaseModel):
    query: str
    results: list[WebSearchResult] = Field(default_factory=list)
    provider: str = ""


class WebSearchRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    include_domains: list[str] = Field(default_factory=list, max_length=5)
    exclude_domains: list[str] = Field(default_factory=list, max_length=20)
    max_results: int = Field(default=4, ge=1, le=10)
    recency_days: int | None = Field(default=7, ge=1, le=365)


def _host(url: str) -> str:
    try:
        return urlparse(url).hostname or ""
    except Exception:
        return ""


def apply_domain_filter(
    results: list[dict],
    *,
    include_domains: list[str],
    exclude_domains: list[str],
) -> list[dict]:
    inc = {d.lower() for d in include_domains}
    exc = {d.lower() for d in exclude_domains}
    kept: list[dict] = []
    for r in results:
        h = _host(str(r.get("url", ""))).lower()
        if exc and any(h == d or h.endswith("." + d) for d in exc):
            continue
        if inc and not any(h == d or h.endswith("." + d) for d in inc):
            continue
        kept.append(r)
    return kept
