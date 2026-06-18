"""PDF parser. Uses pdfplumber or pymupdf. Falls back to OCR if DIGISEARCH_OCR_ENABLED=true."""

from __future__ import annotations

import io
import logging
import os
import uuid
from pathlib import Path

from digisearch.core.models import Document
from digisearch.ingestion.base import Parser

logger = logging.getLogger(__name__)

# OCR path: pdf2image / pytesseract surface OSError, ValueError, RuntimeError, ImportError (DESLOP-017).
_OCR_ERRORS = (OSError, ValueError, RuntimeError, ImportError)

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

# OCR support: requires pytesseract + pdf2image. Enabled by DIGISEARCH_OCR_ENABLED=true.
_OCR_ENABLED = os.environ.get("DIGISEARCH_OCR_ENABLED", "").lower() in ("1", "true", "yes")
_OCR_AVAILABLE = False

if _OCR_ENABLED:
    try:
        import pytesseract as _pytesseract  # type: ignore[import-untyped]
        import pdf2image as _pdf2image  # type: ignore[import-untyped]

        _OCR_AVAILABLE = True
    except ImportError:
        logger.warning(
            "DIGISEARCH_OCR_ENABLED is set but pytesseract/pdf2image are not installed. "
            "Install them with: pip install digisearch[ocr]  (pytesseract + pdf2image)"
        )


def _extract_text_pdfplumber(raw: bytes) -> str:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return "\n".join(p.extract_text() or "" for p in pdf.pages)


def _extract_text_pymupdf(raw: bytes) -> str:
    import pymupdf

    doc = pymupdf.open(stream=raw, filetype="pdf")
    return "\n".join(p.get_text() for p in doc)


def _extract_text_ocr(raw: bytes) -> str:
    """OCR fallback using pytesseract + pdf2image. Called only when _OCR_AVAILABLE=True."""
    images = _pdf2image.convert_from_bytes(raw)
    pages: list[str] = []
    for img in images:
        text = _pytesseract.image_to_string(img)
        pages.append(text or "")
    return "\n".join(pages)


class PDFParser(Parser):
    """Parse PDF.

    Strategy:
    1. Try pdfplumber (preferred) or pymupdf to extract the text layer.
    2. If the text layer is empty *and* DIGISEARCH_OCR_ENABLED=true, fall back to
       pytesseract + pdf2image OCR (for scanned/image PDFs).
    3. Otherwise return a placeholder indicating no text was found.

    Set DIGISEARCH_OCR_ENABLED=true and install pytesseract + pdf2image to enable OCR.
    """

    def parse(self, source: str | Path | bytes) -> Document:
        if not _PDF_AVAILABLE:
            raise ImportError("Install pdfplumber or pymupdf for PDF parsing")
        if isinstance(source, bytes):
            content = self._extract_bytes(source)
            src_str = "<bytes>"
            raw = source
        else:
            path = Path(source)
            if path.exists():
                raw = path.read_bytes()
                content = self._extract_bytes(raw)
                src_str = str(path)
            else:
                raise FileNotFoundError(f"PDF source not found: {source}")

        if not content.strip():
            if _OCR_AVAILABLE:
                logger.info("No text layer found in PDF %s — running OCR", src_str)
                try:
                    content = _extract_text_ocr(raw)
                    if content.strip():
                        logger.info("OCR extracted %d chars from %s", len(content), src_str)
                    else:
                        logger.warning("OCR found no text in %s", src_str)
                        content = "[No text extracted from PDF (OCR attempted but found nothing).]"
                except _OCR_ERRORS as e:
                    logger.error("OCR failed for %s: %s", src_str, e)
                    content = f"[OCR failed: {e}]"
            elif _OCR_ENABLED:
                # OCR was requested but deps unavailable — already warned at import
                content = "[No text extracted from PDF. OCR dependencies not installed.]"
            else:
                content = (
                    "[No text extracted from PDF. Set DIGISEARCH_OCR_ENABLED=true to enable OCR.]"
                )

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
            return _extract_text_pdfplumber(raw)
        if _PDF_IMPL == "pymupdf":
            return _extract_text_pymupdf(raw)
        return ""

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext == ".pdf"
