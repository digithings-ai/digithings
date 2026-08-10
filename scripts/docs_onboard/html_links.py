"""Extract same-document links from HTML (stdlib only)."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import urljoin, urlparse

_DOC_EXTS = (".pdf", ".doc", ".docx")


class _HrefCollector(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.hrefs: list[tuple[str, str]] = []  # (href, link_text)
        self._capture = False
        self._buf: list[str] = []
        self._href: str | None = None
        self.title: str = ""
        self._in_title = False

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr_map = {k: (v or "") for k, v in attrs}
        if tag == "a":
            href = attr_map.get("href", "").strip()
            if href and not href.startswith(("#", "mailto:", "javascript:")):
                self._href = href
                self._capture = True
                self._buf = []
        elif tag == "title":
            self._in_title = True

    def handle_endtag(self, tag: str) -> None:
        if tag == "a" and self._capture and self._href is not None:
            text = re.sub(r"\s+", " ", "".join(self._buf)).strip()
            self.hrefs.append((self._href, text))
            self._capture = False
            self._href = None
            self._buf = []
        elif tag == "title":
            self._in_title = False

    def handle_data(self, data: str) -> None:
        if self._capture:
            self._buf.append(data)
        if self._in_title:
            self.title += data


def extract_title(html: str) -> str:
    """Return ``<title>`` text, or empty string."""
    collector = _HrefCollector()
    try:
        collector.feed(html)
    except Exception:  # pragma: no cover - malformed HTML should not crash crawl
        return ""
    return collector.title.strip()


def extract_links(html: str, base_url: str) -> list[tuple[str, str]]:
    """Return absolute ``(url, link_text)`` pairs from ``html``.

    Fragments and non-http(s) schemes are dropped. Relative links resolve
    against ``base_url``.
    """
    collector = _HrefCollector()
    try:
        collector.feed(html)
    except Exception:  # pragma: no cover
        return []
    out: list[tuple[str, str]] = []
    seen: set[str] = set()
    for href, text in collector.hrefs:
        abs_url = urljoin(base_url, href)
        parsed = urlparse(abs_url)
        if parsed.scheme not in ("http", "https"):
            continue
        # Drop fragment for crawl identity.
        clean = abs_url.split("#", 1)[0]
        if clean in seen:
            continue
        seen.add(clean)
        out.append((clean, text))
    return out


def looks_like_document(url: str) -> bool:
    """True when the URL path ends with a known document extension."""
    path = urlparse(url).path.lower()
    return any(path.endswith(ext) for ext in _DOC_EXTS)
