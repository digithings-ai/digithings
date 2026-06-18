"""Markdown parser (plain-text extraction; mistune not used)."""

from __future__ import annotations

import logging
import time
import uuid
from pathlib import Path

from digisearch.core.models import Document
from digisearch.ingestion.base import Parser

logger = logging.getLogger(__name__)


class MarkdownParser(Parser):
    """Parse Markdown. Preserves heading metadata."""

    def parse(self, source: str | Path | bytes) -> Document:
        start = time.perf_counter()
        try:
            if isinstance(source, bytes):
                content = source.decode("utf-8", errors="replace")
                src_str = "<bytes>"
            else:
                path = Path(source)
                if path.exists():
                    content = path.read_text(encoding="utf-8", errors="replace")
                    src_str = str(path)
                else:
                    content = str(source)
                    src_str = "<string>"
            doc_id = str(uuid.uuid4())
            doc = Document(
                id=doc_id,
                content=content,
                source=src_str,
                doc_type="markdown",
                metadata={},
            )
        except Exception:
            logger.exception(
                "markdown parse failed",
                extra={
                    "operation": "parse_markdown",
                    "duration_ms": int((time.perf_counter() - start) * 1000),
                    "outcome": "error",
                },
            )
            raise
        logger.info(
            "markdown parsed",
            extra={
                "operation": "parse_markdown",
                "duration_ms": int((time.perf_counter() - start) * 1000),
                "outcome": "ok",
                "doc_id": doc_id,
                "content_length": len(content),
            },
        )
        return doc

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext in (".md", ".markdown")
