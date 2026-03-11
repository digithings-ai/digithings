"""Markdown parser. Uses mistune."""

from __future__ import annotations

import uuid
from pathlib import Path

from digisearch.core.models import Document
from digisearch.ingestion.base import Parser

try:
    import mistune
    _MISTUNE_AVAILABLE = True
except ImportError:
    _MISTUNE_AVAILABLE = False


class MarkdownParser(Parser):
    """Parse Markdown. Preserves heading metadata."""

    def parse(self, source: str | Path | bytes) -> Document:
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
        return Document(
            id=doc_id,
            content=content,
            source=src_str,
            doc_type="markdown",
            metadata={},
        )

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext in (".md", ".markdown")
