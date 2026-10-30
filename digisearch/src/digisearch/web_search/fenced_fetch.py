"""Open one page for a pinned tenant: fetch it inside the tenant's site fence.

This is the open-page mode of ``web_search`` (``url`` + ``fence`` arguments),
which only a pinned tenant's tool definition offers. It
reads one full page on an allowed site, so the model can follow links and
discover subdomains instead of seeing only search snippets. Never indexes.

The fence (``fence.py``) is enforced on the requested URL and on **every
redirect hop** (digifetch ``url_guard``), after the SSRF guard. A hop outside
the fence stops the fetch: off-fence content never comes back. Links found on
the page are returned only when they are themselves inside the fence.

The fetch is bounded: a byte cap on the streamed body
(``MAX_PAGE_BYTES``), a text-only content-type allowlist
(``ALLOWED_CONTENT_TYPES``) and one overall deadline across every hop and
chunk (``FETCH_DEADLINE_S``). These apply to this path only; digifetch's
defaults are unchanged.

A live page behind a bot challenge (or a failed fetch) falls back to the
tenant's pre-crawled page corpus when one is named, exactly like web_search
enrichment; the result says which source served it.
"""

from __future__ import annotations

import logging
import re
import time
from html.parser import HTMLParser
from typing import Any
from urllib.parse import urljoin, urlsplit, urlunsplit

from pydantic import BaseModel, Field, ValidationError

from digisearch.web_search.extractor import extract_markdown
from digisearch.web_search.fence import (
    FenceRefusedError,
    clean_pins,
    fence_guard,
    url_in_fence,
)
from digisearch.web_search.page_corpus import corpus_page_text, is_challenge_page

logger = logging.getLogger(__name__)

#: Largest page body read (bytes); the stream stops past this.
MAX_PAGE_BYTES = 3 * 1024 * 1024
#: Whole fetch (all redirect hops and body chunks), seconds.
FETCH_DEADLINE_S = 20.0
#: Media types read as a page. A missing Content-Type is treated as HTML.
ALLOWED_CONTENT_TYPES = frozenset(
    {"text/html", "application/xhtml+xml", "text/plain", "text/markdown"}
)
#: Default and ceiling for the page text handed back (characters).
DEFAULT_MAX_CHARS = 12000
MAX_CHARS_CEILING = 40000
#: Most in-fence links returned per page.
MAX_LINKS = 80


class WebFetchRequest(BaseModel):
    url: str = Field(min_length=8, max_length=2048)
    # The tenant's pins. Required and non-empty: an unfenced fetch is not
    # something this tool does (the open web has web_search).
    fence: list[str] = Field(min_length=1, max_length=50)
    page_corpus: str | None = Field(
        default=None, max_length=64, pattern=r"^[a-z0-9][a-z0-9-]{0,63}$"
    )
    max_chars: int = Field(default=DEFAULT_MAX_CHARS, ge=500, le=MAX_CHARS_CEILING)


class WebFetchData(BaseModel):
    """One opened page (the ``data`` of an open-page ``web_search`` call)."""

    url: str
    final_url: str
    title: str = ""
    content: str = ""
    truncated: bool = False
    links: list[str] = Field(default_factory=list)
    source: str = "live"  # live | page_corpus
    note: str = ""


class _LinkParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[str] = []
        self.title = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag == "a":
            for k, v in attrs:
                if k == "href" and v:
                    self.hrefs.append(v)
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._in_title and len(self.title) < 300:
            self.title += data


class _TextParser(HTMLParser):
    """Visible page text (no script/style/svg), for pages the extractor under-reads."""

    _SKIP = frozenset({"script", "style", "noscript", "svg", "template", "head"})

    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in self._SKIP:
            self._skip += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in self._SKIP and self._skip:
            self._skip -= 1

    def handle_data(self, data: str) -> None:
        if not self._skip and data.strip():
            self.parts.append(" ".join(data.split()))


def _visible_text(html: str) -> str:
    parser = _TextParser()
    try:
        parser.feed(html)
    except Exception:
        return ""
    return "\n".join(parser.parts)


_MD_LINK_RE = re.compile(r"\]\((https?://[^)\s]+)\)")


def _clean_link(base: str, href: str) -> str | None:
    href = href.strip()
    if not href or href.startswith(("#", "mailto:", "tel:", "javascript:", "data:")):
        return None
    try:
        parts = urlsplit(urljoin(base, href))
    except ValueError:
        return None
    if parts.scheme not in ("http", "https") or not parts.netloc:
        return None
    return urlunsplit((parts.scheme, parts.netloc.lower(), parts.path or "/", parts.query, ""))


def fenced_links(base: str, hrefs: list[str], pins: list[str]) -> list[str]:
    """Absolute, de-duplicated links from ``hrefs`` that sit inside the fence."""
    out: list[str] = []
    for href in hrefs:
        link = _clean_link(base, href)
        if link and link not in out and url_in_fence(link, pins):
            out.append(link)
            if len(out) >= MAX_LINKS:
                break
    return out


def _from_corpus(req: WebFetchRequest, pins: list[str], reason: str) -> dict[str, Any] | None:
    text = corpus_page_text(req.page_corpus, req.url) if req.page_corpus else None
    if not text:
        return None
    return {
        "url": req.url,
        "final_url": req.url,
        "title": "",
        "content": text[: req.max_chars],
        "truncated": len(text) > req.max_chars,
        "links": fenced_links(req.url, _MD_LINK_RE.findall(text), pins),
        "source": "page_corpus",
        "note": reason,
    }


def fetch_page(req: WebFetchRequest, *, fetcher: Any | None = None) -> dict[str, Any]:
    """Fetch ``req.url`` inside ``req.fence``; raise ``FenceRefusedError`` when it may not."""
    pins = clean_pins(req.fence)
    if not pins:
        raise FenceRefusedError("no allowed sites")
    if not url_in_fence(req.url, pins):
        raise FenceRefusedError(f"outside the allowed sites: {req.url}")
    from digifetch import HttpFetcher

    from digisearch.web_search.service import WebSearchConfig

    config = WebSearchConfig.from_env()
    owns = fetcher is None
    active = fetcher or HttpFetcher(
        timeout=min(config.fetch_timeout, FETCH_DEADLINE_S),
        max_bytes=MAX_PAGE_BYTES,
        allowed_hosts=config.fetch_allowed_hosts,
    )
    deadline = time.monotonic() + FETCH_DEADLINE_S
    try:
        try:
            fetched = active.download(req.url, url_guard=fence_guard(pins), deadline=deadline)
            html = _page_text(fetched.content, fetched.content_type)
        except FenceRefusedError:
            # A redirect left the fence (e.g. to a login host): nothing from
            # the far side is returned, not even through the corpus.
            raise
        except Exception as exc:
            fallback = _from_corpus(req, pins, f"live fetch failed: {type(exc).__name__}")
            if fallback is not None:
                return fallback
            raise
        if is_challenge_page(fetched.status_code, fetched.url, html):
            fallback = _from_corpus(req, pins, "live page is a bot challenge")
            if fallback is not None:
                return fallback
            raise RuntimeError("the live page is a bot challenge and no saved copy exists")
        md = extract_markdown(html, url=fetched.url) or ""
        # Site-builder / SPA pages defeat the article
        # extractor: keep the page's visible text when it holds far more.
        visible = _visible_text(html)
        if len(visible) > 3 * max(len(md), 300):
            md = visible
        parser = _LinkParser()
        try:
            parser.feed(html)
        except Exception:  # malformed HTML: keep the text, lose the links
            logger.info("open page: link parse failed for %s", fetched.url)
        if not md.strip():
            fallback = _from_corpus(req, pins, "no readable text on the live page")
            if fallback is not None:
                return fallback
        return {
            "url": req.url,
            "final_url": fetched.url,
            "title": " ".join(parser.title.split()),
            "content": md[: req.max_chars],
            "truncated": len(md) > req.max_chars,
            "links": fenced_links(fetched.url, parser.hrefs, pins),
            "source": "live",
        }
    finally:
        if owns:
            active.close()


class UnsupportedContentError(ValueError):
    """The page is not text (a PDF, image, archive, ...) or is over the byte cap."""


def _page_text(content: bytes, content_type: str | None) -> str:
    """Decode a text page body; refuse non-text media types and oversize bodies.

    The cap is re-checked here so an injected fetcher (whatever its own
    ``max_bytes``) is held to the same limit.
    """
    raw_type = (content_type or "").strip()
    media, _, params = raw_type.partition(";")
    media = media.strip().lower()
    if media and media not in ALLOWED_CONTENT_TYPES:
        raise UnsupportedContentError(f"not a text page (content type {media})")
    if len(content) > MAX_PAGE_BYTES:
        raise UnsupportedContentError(f"page is larger than {MAX_PAGE_BYTES} bytes")
    charset = "utf-8"
    for param in params.split(";"):
        key, _, value = param.partition("=")
        if key.strip().lower() == "charset" and value.strip():
            charset = value.strip().strip('"').strip("'")
    try:
        return content.decode(charset, errors="replace")
    except LookupError:  # unknown charset label
        return content.decode("utf-8", errors="replace")


def invoke_web_fetch(arguments: dict[str, Any], *, fetcher: Any | None = None) -> dict[str, Any]:
    """Orchestrator envelope for open-page ``web_search``: ``{"ok", "data"|"error"}``. Never raises."""
    try:
        req = WebFetchRequest(
            **{k: v for k, v in arguments.items() if k in WebFetchRequest.model_fields}
        )
    except ValidationError as exc:
        from digisearch.web_search.models import summarize_validation_error

        return {"ok": False, "error": f"invalid open-page input: {summarize_validation_error(exc)}"}
    try:
        return {"ok": True, "data": fetch_page(req, fetcher=fetcher)}
    except FenceRefusedError as exc:
        return {"ok": False, "error": f"fence_refused: {exc}"}
    except Exception as exc:
        from digisearch.web_search.service import _scrub_provider_detail

        detail = _scrub_provider_detail(str(exc) or type(exc).__name__)
        return {"ok": False, "error": f"open page failed: {detail[:300]}"}
