"""TesseractOCR - local Tesseract."""

from __future__ import annotations

from pathlib import Path

from digisearch.ingestion.ocr.base import OCRProvider

try:
    import pytesseract
    from PIL import Image
    _TESS_AVAILABLE = True
except ImportError:
    _TESS_AVAILABLE = False


class TesseractOCR(OCRProvider):
    """Tesseract OCR. Good for offline/on-prem."""

    def extract_text(self, image: bytes | Path) -> str:
        if not _TESS_AVAILABLE:
            raise ImportError("Install pytesseract and Pillow for Tesseract OCR")
        if isinstance(image, Path):
            img = Image.open(image)
        else:
            from io import BytesIO
            img = Image.open(BytesIO(image))
        return pytesseract.image_to_string(img)
