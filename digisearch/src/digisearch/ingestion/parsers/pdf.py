"""PDF parser. Uses pdfplumber or pymupdf. Falls back to OCR if no text layer."""

from __future__ import annotations

import io
import uuid
from pathlib import Path

from digisearch.core.models import Document
from digisearch.ingestion.base import Parser

_PDF_AVAILABLE = False
_PDF_IMPL = None

try:
    import pdfplumber
    _PDF_AVAILABLE = True
    _PDF_IMPL = "pdfplumber"
except ImportError:
    try:
        import pymupdf
        _PDF_AVAILABLE = True
        _PDF_IMPL = "pymupdf"
    except ImportError:
        pass


class PDFParser(Parser):
    """Parse PDF. Uses pdfplumber or pymupdf. OCR fallback not yet wired."""

    def parse(self, source: str | Path | bytes) -> Document:
        if not _PDF_AVAILABLE:
            raise ImportError("Install pdfplumber or pymupdf for PDF parsing")
        if isinstance(source, bytes):
            content = self._extract_bytes(source)
            src_str = "<bytes>"
        else:
            path = Path(source)
            if path.exists():
                content = self._extract_bytes(path.read_bytes())
                src_str = str(path)
            else:
                raise FileNotFoundError(f"PDF source not found: {source}")
        if not content.strip():
            content = "[No text extracted from PDF. OCR not yet wired.]"
        doc_id = str(uuid.uuid4())
        return Document(
            id=doc_id,
            content=content,
            source=src_str,
            doc_type="pdf",
            metadata={},
        )

    def _extract_bytes(self, raw: bytes) -> str:
        if _PDF_IMPL == "pdfplumber":
            import pdfplumber
            with pdfplumber.open(io.BytesIO(raw)) as pdf:
                return "\n".join(p.extract_text() or "" for p in pdf.pages)
        if _PDF_IMPL == "pymupdf":
            import pymupdf
            doc = pymupdf.open(stream=raw, filetype="pdf")
            return "\n".join(p.get_text() for p in doc)
        return ""

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext == ".pdf"
