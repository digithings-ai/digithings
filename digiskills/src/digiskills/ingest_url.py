"""Remote-source corpus builder (docs pages / OpenAPI specs over HTTP).

Requires the ``digiskills[ingest]`` extra (``digifetch``). Lazily imported —
``import digiskills`` never pulls in ``digifetch`` or ``httpx``; only calling
:class:`UrlCorpusBuilder` does.

A single URL fetch failure does not abort the whole build: it is skipped and
the corpus is marked ``truncated`` (mirrors the fail-soft convention used by
``digillm.web_search`` — best-effort grounding, not an all-or-nothing gate).
"""

from __future__ import annotations

import logging
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from digiskills.models import Corpus, SkillSource, SourceDocument, SourceKind

if TYPE_CHECKING:
    # Type-only: keeps `import digiskills.ingest_url` digifetch-free at runtime
    # (see the lazy `from digifetch import HttpFetcher` in `build`, below).
    from digifetch import HttpFetcher

logger = logging.getLogger(__name__)

DEFAULT_MAX_URLS = 50
DEFAULT_MAX_TOTAL_CHARS = 2_000_000
DEFAULT_MAX_DOC_CHARS = 200_000

_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg"})


class _HtmlTextExtractor(HTMLParser):
    """Minimal HTML -> plain-text extractor (stdlib only, no bs4 dependency).

    Good enough for doc pages feeding an LLM synthesis prompt; not a general
    HTML-to-Markdown converter. Drops ``<script>``/``<style>`` content.
    """

    def __init__(self) -> None:
        super().__init__()
        self._chunks: list[str] = []
        self._skip_depth = 0

    def handle_starttag(self, tag: str, attrs: list[tuple[str, str | None]]) -> None:
        if tag in _SKIP_TAGS:
            self._skip_depth += 1

    def handle_endtag(self, tag: str) -> None:
        if tag in _SKIP_TAGS and self._skip_depth > 0:
            self._skip_depth -= 1

    def handle_data(self, data: str) -> None:
        if self._skip_depth == 0 and data.strip():
            self._chunks.append(data.strip())

    def text(self) -> str:
        return "\n".join(self._chunks)


def _extract_text(body: str, content_type: str) -> str:
    if "html" in content_type:
        extractor = _HtmlTextExtractor()
        extractor.feed(body)
        return extractor.text()
    return body


class UrlCorpusBuilder:
    """Builds a :class:`Corpus` by fetching a list of docs/OpenAPI URLs.

    Args:
        max_urls: Stop after fetching this many URLs.
        max_total_chars: Stop once the accumulated corpus reaches this many characters.
        max_doc_chars: Truncate any single fetched document to this many characters.
        fetcher: Inject a pre-built ``digifetch.HttpFetcher`` (e.g. one wired to
            an ``httpx.MockTransport`` in tests). When omitted, a default
            fetcher is lazily constructed — and closed — per :meth:`build` call.
    """

    def __init__(
        self,
        *,
        max_urls: int = DEFAULT_MAX_URLS,
        max_total_chars: int = DEFAULT_MAX_TOTAL_CHARS,
        max_doc_chars: int = DEFAULT_MAX_DOC_CHARS,
        fetcher: "HttpFetcher | None" = None,
    ) -> None:
        self.max_urls = max_urls
        self.max_total_chars = max_total_chars
        self.max_doc_chars = max_doc_chars
        self._fetcher = fetcher

    def build(self, source: SkillSource) -> Corpus:
        """Fetch ``source.urls`` into a :class:`Corpus`.

        Raises:
            ValueError: ``source.kind`` is not ``URLS``.
            ImportError: no ``fetcher`` was injected and the ``digiskills[ingest]``
                extra (``digifetch``) is not installed.
        """
        if source.kind is not SourceKind.URLS:
            raise ValueError(f"UrlCorpusBuilder requires kind=URLS, got {source.kind}")

        owns_fetcher = self._fetcher is None
        if self._fetcher is not None:
            fetcher = self._fetcher
        else:
            from digifetch import HttpFetcher  # lazy: keeps the core import digifetch-free

            fetcher = HttpFetcher()

        documents: list[SourceDocument] = []
        total_chars = 0
        truncated = False

        try:
            for url in source.urls[: self.max_urls]:
                try:
                    result = fetcher.fetch(url)
                except Exception as exc:  # noqa: BLE001 — one bad URL must not abort the build
                    logger.warning("skipping %s: fetch failed (%s)", url, exc)
                    truncated = True
                    continue

                text = _extract_text(result.text, result.content_type).strip()
                if not text:
                    continue
                if len(text) > self.max_doc_chars:
                    text = text[: self.max_doc_chars]
                    truncated = True

                remaining_budget = self.max_total_chars - total_chars
                if remaining_budget <= 0:
                    truncated = True
                    break
                if len(text) > remaining_budget:
                    text = text[:remaining_budget]
                    truncated = True

                content_type = "application/json" if "json" in result.content_type else "text/plain"
                documents.append(
                    SourceDocument(
                        origin=result.url,
                        title=result.url,
                        content=text,
                        content_type=content_type,
                    )
                )
                total_chars += len(text)
                if total_chars >= self.max_total_chars:
                    truncated = True
                    break
        finally:
            if owns_fetcher:
                fetcher.close()

        if len(source.urls) > self.max_urls:
            truncated = True

        return Corpus(documents=documents, truncated=truncated)
