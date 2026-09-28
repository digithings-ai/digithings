"""Non-indexing single-URL fetch plus markdown extract for web grounding (R3).

Owns one SSRF-guarded digifetch ``HttpFetcher.download()`` and the landed
``extract_markdown`` seam. This module never indexes: it must not import or
call the pipeline ingest path, so fetched pages cannot leak into the corpus.
"""

from __future__ import annotations

from collections.abc import Iterable
from typing import TYPE_CHECKING

from digisearch.web_search.extractor import extract_markdown

if TYPE_CHECKING:
    from digifetch import HttpFetcher


def _effective_allowed_hosts(allowed_hosts: Iterable[str]) -> tuple[str, ...]:
    """Explicit hosts win; otherwise reuse the web-search env allow-list."""
    explicit = tuple(h.strip().lower() for h in allowed_hosts if h and h.strip())
    if explicit:
        return explicit
    try:
        from digisearch.web_search.service import WebSearchConfig

        return tuple(WebSearchConfig.from_env().fetch_allowed_hosts)
    except Exception:
        return ()


def _decode_content(content: bytes, content_type: str) -> str:
    """Decode download bytes with the declared charset, defaulting to utf-8."""
    charset = "utf-8"
    for part in content_type.split(";")[1:]:
        name, _, value = part.partition("=")
        if name.strip().lower() == "charset" and value.strip():
            charset = value.strip().strip("\"'") or "utf-8"
            break
    try:
        return content.decode(charset, errors="replace")
    except (LookupError, ValueError):
        return content.decode("utf-8", errors="replace")


def _owned_fetcher(timeout: float, allowed_hosts: tuple[str, ...]) -> HttpFetcher:
    from digifetch import HttpFetcher

    return HttpFetcher(timeout=timeout, allowed_hosts=allowed_hosts)


def fetch_markdown(
    url: str,
    *,
    timeout: float = 15.0,
    allowed_hosts: Iterable[str] = (),
    fetcher: HttpFetcher | None = None,
) -> str:
    """Fetch *url* and return extracted markdown; the page is never indexed.

    Downloads once through the digifetch SSRF guard (an injected *fetcher*
    is used as-is and is not closed), decodes with the response charset,
    then runs the landed ``extract_markdown``. Returns ``""`` when nothing
    is extractable. *timeout* mirrors ``WebSearchConfig.fetch_timeout``;
    explicit *allowed_hosts* win over ``DIGISEARCH_FETCH_ALLOWED_HOSTS``.
    """
    owns_fetcher = fetcher is None
    active = (
        fetcher
        if fetcher is not None
        else _owned_fetcher(timeout, _effective_allowed_hosts(allowed_hosts))
    )
    try:
        downloaded = active.download(url)
        html = _decode_content(downloaded.content, downloaded.content_type)
        return extract_markdown(html, url=downloaded.url)
    finally:
        if owns_fetcher:
            try:
                active.close()
            except Exception:
                pass
