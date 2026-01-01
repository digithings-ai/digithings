"""OCRProvider abstract interface."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path


class OCRProvider(ABC):
    """Abstract OCR provider. Extract text from images."""

    @abstractmethod
    def extract_text(self, image: bytes | Path) -> str:
        """Extract text from image."""
        ...
