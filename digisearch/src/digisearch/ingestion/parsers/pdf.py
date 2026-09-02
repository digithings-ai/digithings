"""PDF parser. Uses pdfplumber or pymupdf. Falls back to OCR if DIGISEARCH_OCR_ENABLED=true."""

from __future__ import annotations

import io
import logging
import os
from pathlib import Path

from digisearch.core.models import Document, Segment
from digisearch.core.stable_ids import stable_doc_id
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
        import pdf2image as _pdf2image  # type: ignore[import-untyped]
        import pytesseract as _pytesseract  # type: ignore[import-untyped]

        _OCR_AVAILABLE = True
    except ImportError:
        logger.warning(
            "DIGISEARCH_OCR_ENABLED is set but pytesseract/pdf2image are not installed. "
            "Install them with: pip install digisearch[ocr]  (pytesseract + pdf2image)"
        )


def _extract_pages_pdfplumber(raw: bytes) -> list[str]:
    import pdfplumber

    with pdfplumber.open(io.BytesIO(raw)) as pdf:
        return [p.extract_text() or "" for p in pdf.pages]


def _extract_pages_pymupdf(raw: bytes) -> list[str]:
    import pymupdf

    doc = pymupdf.open(stream=raw, filetype="pdf")
    return [p.get_text() for p in doc]


def _extract_pages(raw: bytes) -> list[str]:
    """Per-page text. Page boundaries are preserved here and become Document.segments."""
    if _PDF_IMPL == "pdfplumber":
        return _extract_pages_pdfplumber(raw)
    if _PDF_IMPL == "pymupdf":
        return _extract_pages_pymupdf(raw)
    return []


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
            raw = source
            src_str = "<bytes>"
        else:
            path = Path(source)
            if not path.exists():
                raise FileNotFoundError(f"PDF source not found: {source}")
            raw = path.read_bytes()
            src_str = str(path)
        pages = _extract_pages(raw)
        content = "\n".join(pages)

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

        segments: list[Segment] = []
        for number, page_text in enumerate(pages, start=1):
            stripped = page_text.strip()
            if not stripped:
                continue
            segments.append(
                Segment(
                    index=len(segments),
                    label=f"page:{number}",
                    text=stripped,
                    metadata={"page": number},
                )
            )

        doc_id = stable_doc_id(source=src_str, content=content)
        return Document(
            id=doc_id,
            content=content,
            source=src_str,
            doc_type="pdf",
            metadata={},
            segments=segments,
        )

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext == ".pdf"
