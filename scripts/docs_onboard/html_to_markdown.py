"""Lightweight HTML → markdown for vault notes and digisearch ingest (stdlib only)."""

from __future__ import annotations

import re
from html.parser import HTMLParser


class _ToMarkdown(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.parts: list[str] = []
        self._skip = 0
        self._in_pre = False
        self._href: str | None = None
        self._link_buf: list[str] = []

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        attr = {k: (v or "") for k, v in attrs}
        if tag in ("script", "style", "nav", "footer", "header"):
            self._skip += 1
            return
        if self._skip:
            return
        if tag in ("br",):
            self.parts.append("\n")
        elif tag in ("p", "div", "section", "article", "li"):
            self.parts.append("\n")
        elif tag in ("h1", "h2", "h3", "h4", "h5", "h6"):
            level = int(tag[1])
            self.parts.append("\n" + "#" * level + " ")
        elif tag == "a":
            self._href = attr.get("href") or None
            self._link_buf = []
        elif tag == "pre":
            self._in_pre = True
            self.parts.append("\n```\n")
        elif tag == "code" and not self._in_pre:
            self.parts.append("`")
        elif tag == "ul" or tag == "ol":
            self.parts.append("\n")

    def handle_endtag(self, tag: str) -> None:
        if tag in ("script", "style", "nav", "footer", "header"):
            if self._skip:
                self._skip -= 1
            return
        if self._skip:
            return
        if tag == "a" and self._href is not None:
            label = re.sub(r"\s+", " ", "".join(self._link_buf)).strip() or self._href
            self.parts.append(f"[{label}]({self._href})")
            self._href = None
            self._link_buf = []
        elif tag == "pre":
            self._in_pre = False
            self.parts.append("\n```\n")
        elif tag == "code" and not self._in_pre:
            self.parts.append("`")
        elif tag in ("p", "div", "h1", "h2", "h3", "h4", "h5", "h6", "li"):
            self.parts.append("\n")

    def handle_data(self, data: str) -> None:
        if self._skip:
            return
        if self._href is not None:
            self._link_buf.append(data)
            return
        if self._in_pre:
            self.parts.append(data)
        else:
            self.parts.append(re.sub(r"\s+", " ", data))


def html_to_markdown(html: str) -> str:
    """Convert HTML to a rough markdown body for digivault notes and search ingest."""
    parser = _ToMarkdown()
    try:
        parser.feed(html)
    except Exception:
        # Fall back to stripped tags on catastrophic parse failure.
        return re.sub(r"<[^>]+>", " ", html)
    text = "".join(parser.parts)
    text = re.sub(r"\n{3,}", "\n\n", text)
    return text.strip() + "\n"
