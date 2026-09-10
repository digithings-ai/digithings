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


def recency_days_to_ddgs_timelimit(recency_days: int | None) -> str | None:
    """Map recency_days to a ddgs ``text()`` timelimit (d/w/m/y); None omits it."""
    if recency_days is None:
        return None
    if recency_days <= 1:
        return "d"
    if recency_days <= 7:
        return "w"
    if recency_days <= 31:
        return "m"
    return "y"


def recency_days_to_searxng_time_range(recency_days: int | None) -> str | None:
    """Map recency_days to a searxng ``time_range`` (day/month/year); None omits it.

    searxng documents only day/month/year (no week bucket), so sub-month
    windows above a day map to the next-coarser month superset.
    """
    if recency_days is None:
        return None
    if recency_days <= 1:
        return "day"
    if recency_days <= 31:
        return "month"
    return "year"


def summarize_validation_error(exc: Exception) -> str:
    """Render a pydantic ValidationError as a single clean line (never a traceback)."""
    from pydantic import ValidationError

    assert isinstance(exc, ValidationError)
    parts = []
    for err in exc.errors():
        loc = ".".join(str(p) for p in err.get("loc", ())) or "value"
        parts.append(f"{loc}: {err.get('msg', 'invalid')}")
    return "; ".join(parts) or "invalid input"


def _normalize_domains(domains: list[str]) -> set[str]:
    """Strip/lower/drop-empty domain entries once, so padded/empty lists behave."""
    return {d.strip().lower() for d in domains if d.strip()}


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
    inc = _normalize_domains(include_domains)
    exc = _normalize_domains(exclude_domains)
    kept: list[dict] = []
    for r in results:
        h = _host(str(r.get("url", ""))).lower()
        if exc and any(h == d or h.endswith("." + d) for d in exc):
            continue
        if inc and not any(h == d or h.endswith("." + d) for d in inc):
            continue
        kept.append(r)
    return kept
