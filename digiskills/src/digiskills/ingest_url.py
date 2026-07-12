"""Remote-source corpus builder (docs pages / OpenAPI specs over HTTP).

Requires the ``digiskills[ingest]`` extra (``digifetch``). Lazily imported —
``import digiskills`` never pulls in ``digifetch`` or ``httpx``; only calling
:class:`UrlCorpusBuilder` does.

A single URL fetch failure does not abort the whole build: it is skipped and
the corpus is marked ``truncated`` (mirrors the fail-soft convention used by
``digillm.web_search`` — best-effort grounding, not an all-or-nothing gate).

Security (P3 pre-flight hardening, see ARCHITECTURE.md): every URL is
checked against :func:`digiskills.security.is_allowed_scrape_url` before
*and* after fetching (catches a redirect landing on a blocked host), the
default fetcher this module builds never auto-follows redirects (so a
malicious redirect is never actually requested), fetched bodies are
downloaded through digifetch's byte-capped, streamed ``download()`` instead
of its unbounded ``fetch()``, and ingested text is passed through
:func:`~digiskills.security.redact_secrets` /
:func:`~digiskills.security.scan_for_prompt_injection` before it becomes a
:class:`SourceDocument`, which is marked ``trusted=False``.
"""

from __future__ import annotations

import logging
import re
from html.parser import HTMLParser
from typing import TYPE_CHECKING

from digiskills.models import Corpus, SkillSource, SourceDocument, SourceKind
from digiskills.security import is_allowed_scrape_url, redact_secrets, scan_for_prompt_injection

if TYPE_CHECKING:
    # Type-only: keeps `import digiskills.ingest_url` digifetch-free at runtime
    # (see the lazy `from digifetch import HttpFetcher` in `build`, below).
    from digifetch import HttpFetcher

logger = logging.getLogger(__name__)

DEFAULT_MAX_URLS = 50
DEFAULT_MAX_TOTAL_CHARS = 2_000_000
DEFAULT_MAX_DOC_CHARS = 200_000

_SKIP_TAGS = frozenset({"script", "style", "noscript", "svg"})
_CHARSET_RE = re.compile(r"charset=([\w-]+)", re.IGNORECASE)


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


def _decode_bytes(content: bytes, content_type: str) -> str:
    """Decode a downloaded body using its declared charset (utf-8 fallback).

    Manual decode step for the ``download()`` byte-cap switch below — unlike
    ``fetch()``'s ``response.text``, ``DownloadResult.content`` is raw bytes.
    """
    match = _CHARSET_RE.search(content_type or "")
    encoding = match.group(1) if match else "utf-8"
    try:
        return content.decode(encoding, errors="replace")
    except LookupError:
        return content.decode("utf-8", errors="replace")


class UrlCorpusBuilder:
    """Builds a :class:`Corpus` by fetching a list of docs/OpenAPI URLs.

    Args:
        max_urls: Stop after fetching this many URLs.
        max_total_chars: Stop once the accumulated corpus reaches this many characters.
        max_doc_chars: Truncate any single fetched document to this many characters.
        fetcher: Inject a pre-built ``digifetch.HttpFetcher`` (e.g. one wired to
            an ``httpx.MockTransport`` in tests). When omitted, a default
            fetcher is lazily constructed — and closed — per :meth:`build`
            call, with redirect-following disabled (see :meth:`build`'s
            security note). An injected fetcher's redirect behavior is the
            caller's own responsibility; the post-fetch URL re-check in
            :meth:`build` still applies as defense in depth.
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

        Security: each URL is checked against
        :func:`~digiskills.security.is_allowed_scrape_url` before the fetch
        (blocks obvious SSRF targets — loopback, private/link-local/reserved
        ranges, the cloud metadata address, non-http(s) schemes) *and* again
        against the actually-fetched ``result.url`` afterward, since a
        redirect can land somewhere the original URL didn't point to. The
        default fetcher this method builds (no ``fetcher=`` injected) also
        disables redirect-following outright, so a redirect is never actually
        requested in the first place — the post-fetch check is then a no-op
        for that path and real defense in depth for an injected fetcher that
        does follow redirects. Every fetched document is passed through
        :func:`~digiskills.security.redact_secrets` and
        :func:`~digiskills.security.scan_for_prompt_injection`, and marked
        ``trusted=False`` (surfaced as a compile warning and an untrusted
        banner in the compiled package — see ``synthesize.py``).

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
            import httpx  # lazy: same extra as digifetch

            # follow_redirects=False: a redirect must be re-validated against
            # the SSRF allowlist before it's requested, which digifetch's own
            # default (follow_redirects=True) can't do — so this builder never
            # auto-follows one. A redirect response is simply skipped below.
            fetcher = HttpFetcher(client=httpx.Client(follow_redirects=False))

        documents: list[SourceDocument] = []
        total_chars = 0
        truncated = False
        redacted_count = 0
        injection_flags: list[str] = []

        try:
            for url in source.urls[: self.max_urls]:
                if not is_allowed_scrape_url(url):
                    logger.warning("skipping %s: blocked by SSRF allowlist", url)
                    truncated = True
                    continue

                try:
                    result = fetcher.download(url)
                except Exception as exc:  # noqa: BLE001 — one bad URL must not abort the build
                    logger.warning("skipping %s: fetch failed (%s)", url, exc)
                    truncated = True
                    continue

                if 300 <= result.status_code < 400:
                    logger.warning("skipping %s: redirect not followed (SSRF guard)", url)
                    truncated = True
                    continue
                if not is_allowed_scrape_url(result.url):
                    logger.warning(
                        "skipping %s: fetched URL %s blocked by SSRF allowlist", url, result.url
                    )
                    truncated = True
                    continue

                decoded = _decode_bytes(result.content, result.content_type)
                text = _extract_text(decoded, result.content_type).strip()
                if not text:
                    continue

                text, n_redacted = redact_secrets(text)
                redacted_count += n_redacted
                for flag in scan_for_prompt_injection(text):
                    injection_flags.append(f"{result.url}: {flag}")

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
                        trusted=False,
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

        return Corpus(
            documents=documents,
            truncated=truncated,
            redacted_count=redacted_count,
            injection_flags=injection_flags,
        )
