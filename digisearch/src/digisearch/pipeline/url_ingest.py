"""Minimal URL to index ingest over landed seams (#4055).

Fetches one URL via the shared digifetch client, extracts markdown with the
existing web_search extractor, stages it to a locked temp dir, and indexes it
through the canonical filesystem ingest path. No new policy module, no routes.

``digifetch`` (``[web-search]`` extra) is imported lazily, inside the functions
that need it, so importing this module never requires the extra.
"""

from __future__ import annotations

import os
import shutil
import tempfile
from collections.abc import Iterable, Mapping
from typing import TYPE_CHECKING, Any

import httpx
from pydantic import BaseModel, ConfigDict, Field

from digisearch.embedding.base import EmbeddingProvider
from digisearch.pipeline.ingest import IngestError, ingest_source
from digisearch.web_search.extractor import extract_markdown

if TYPE_CHECKING:
    from digifetch import HttpFetcher

EXTRACTOR = "trafilatura"


class UrlFetchError(IngestError):
    """URL fetch or extract failure, mapped to the ingest error contract."""

    def __init__(
        self,
        message: str,
        *,
        code: str = "url_fetch_failed",
        http_status: int = 502,
    ) -> None:
        super().__init__(message, code=code, http_status=http_status)


class UrlIngestResult(BaseModel):
    """Outcome of one successful URL ingest."""

    model_config = ConfigDict(extra="forbid")

    doc_id: str
    chunks_created: int = Field(ge=0)
    index_name: str
    source_url: str
    final_url: str
    extractor: str = EXTRACTOR


def _effective_allowed_hosts(allowed_hosts: Iterable[str] | None) -> tuple[str, ...]:
    """Operator hatch: explicit arg wins, else web_search config from env."""
    if allowed_hosts is not None:
        return tuple(h.strip().lower() for h in allowed_hosts if h and h.strip())
    try:
        from digisearch.web_search.service import WebSearchConfig

        return tuple(WebSearchConfig.from_env().fetch_allowed_hosts)
    except Exception:
        return ()


def _default_fetcher(allowed: tuple[str, ...]) -> HttpFetcher:
    """Build the owned fetch client, reusing the web_search timeout when set."""
    from digifetch import HttpFetcher

    timeout: float = 15.0
    try:
        from digisearch.web_search.service import WebSearchConfig

        timeout = WebSearchConfig.from_env().fetch_timeout
    except Exception:
        timeout = 15.0
    return HttpFetcher(timeout=timeout, allowed_hosts=allowed)


def _is_supported_content(content_type: str) -> bool:
    """Allow text/* plus xhtml only; reject anything else fail-closed."""
    base = content_type.split(";")[0].strip().lower()
    if not base:
        return False
    if base == "application/xhtml+xml":
        return True
    return base.startswith("text/")


def _decode_content(content: bytes, content_type: str) -> str:
    """Decode download bytes using the declared charset, defaulting to utf-8."""
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


def ingest_url(
    url: str,
    *,
    index_name: str = "default",
    metadata: Mapping[str, Any] | None = None,
    chunker_name: str | None = None,
    embedding_provider: EmbeddingProvider | None = None,
    fetcher: HttpFetcher | None = None,
    allowed_hosts: Iterable[str] | None = None,
) -> UrlIngestResult:
    """Fetch *url*, extract markdown, and index it via the filesystem path.

    Stages markdown to a 0o700 temp dir as ``page.md`` so the existing
    markdown parser handles it, merges ``source_url`` (final URL) and
    ``evidence_tier: web`` into document metadata, and removes the temp
    dir in a ``finally`` block.
    """
    from digifetch import DownloadTooLargeError
    from digifetch.ssrf import SsrfBlockedError, validate_fetch_url

    effective = _effective_allowed_hosts(allowed_hosts)
    try:
        url = validate_fetch_url(url, allowed_hosts=effective)
    except (SsrfBlockedError, ValueError) as exc:
        raise UrlFetchError(
            f"invalid URL {url!r}: {exc}", code="url_invalid", http_status=400
        ) from exc

    owns_fetcher = fetcher is None
    active = fetcher if fetcher is not None else _default_fetcher(effective)
    tmpdir = tempfile.mkdtemp(prefix="digisearch-url-")
    try:
        os.chmod(tmpdir, 0o700)
    except OSError:
        pass
    try:
        try:
            downloaded = active.download(url)
        except SsrfBlockedError as exc:
            raise UrlFetchError(
                f"blocked URL {url!r}: {exc}", code="url_blocked", http_status=400
            ) from exc
        except DownloadTooLargeError as exc:
            raise UrlFetchError(
                f"download too large for {url!r}: {exc}",
                code="url_too_large",
                http_status=413,
            ) from exc
        except httpx.HTTPError as exc:
            raise UrlFetchError(f"fetch failed for {url!r}: {exc}") from exc

        if not _is_supported_content(downloaded.content_type):
            raise UrlFetchError(
                f"unsupported content-type {downloaded.content_type!r} for {url!r}",
                code="url_unsupported_content",
                http_status=415,
            )
        html = _decode_content(downloaded.content, downloaded.content_type)
        markdown = extract_markdown(html, url=downloaded.url)
        if not markdown or not markdown.strip():
            raise UrlFetchError(
                f"no extractable content from {url!r}",
                code="url_empty_extract",
                http_status=422,
            )
        page = os.path.join(tmpdir, "page.md")
        try:
            with open(page, "w", encoding="utf-8") as handle:
                handle.write(markdown)
        except OSError as exc:
            raise UrlFetchError(
                f"failed to stage download for {url!r}: {exc}",
                code="url_stage_failed",
                http_status=503,
            ) from exc
        merged: dict[str, Any] = {
            **(dict(metadata) if metadata else {}),
            "source_url": downloaded.url,
            "evidence_tier": "web",
        }
        result = ingest_source(
            page,
            index_name=index_name,
            metadata=merged,
            chunker_name=chunker_name,
            embedding_provider=embedding_provider,
        )
        return UrlIngestResult(
            doc_id=result.doc_id,
            chunks_created=result.chunks_created,
            index_name=index_name,
            source_url=url,
            final_url=downloaded.url,
            extractor=EXTRACTOR,
        )
    except IngestError:
        raise
    except (OSError, ValueError, RuntimeError) as exc:
        raise UrlFetchError(f"ingest failed for {url!r}: {exc}") from exc
    finally:
        if owns_fetcher:
            try:
                active.close()
            except Exception:
                pass
        shutil.rmtree(tmpdir, ignore_errors=True)


__all__ = ["EXTRACTOR", "UrlFetchError", "UrlIngestResult", "ingest_url"]
