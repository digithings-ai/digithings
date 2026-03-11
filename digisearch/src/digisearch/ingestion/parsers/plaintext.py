"""PlainText parser. Uses chardet for encoding detection."""

from __future__ import annotations

import uuid
from pathlib import Path

from digisearch.core.models import Document
from digisearch.ingestion.base import Parser

try:
    import chardet
    _CHARDET_AVAILABLE = True
except ImportError:
    _CHARDET_AVAILABLE = False


class PlainTextParser(Parser):
    """Parse plain text files. Encoding via chardet."""

    def _decode(self, raw: bytes) -> str:
        if _CHARDET_AVAILABLE:
            enc = chardet.detect(raw)
            return raw.decode(enc.get("encoding") or "utf-8", errors="replace")
        return raw.decode("utf-8", errors="replace")

    def parse(self, source: str | Path | bytes) -> Document:
        if isinstance(source, bytes):
            content = self._decode(source)
            src_str = "<bytes>"
        else:
            path = Path(source)
            if path.exists():
                raw = path.read_bytes()
                content = self._decode(raw)
                src_str = str(path)
            else:
                content = str(source)
                src_str = "<string>"
        doc_id = str(uuid.uuid4())
        return Document(
            id=doc_id,
            content=content,
            source=src_str,
            doc_type="plaintext",
            metadata={},
        )

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext in (".txt", ".text", ".log", "")
