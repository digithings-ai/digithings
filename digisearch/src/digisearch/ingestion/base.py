"""Abstract Parser interface. All parsers return Document."""

from __future__ import annotations

from abc import ABC, abstractmethod
from pathlib import Path

from digisearch.core.models import Document


class Parser(ABC):
    """Abstract parser. All parsers implement parse() and can_parse()."""

    @abstractmethod
    def parse(self, source: str | Path | bytes) -> Document:
        """Parse source into Document."""
        ...

    def can_parse(self, source: str) -> bool:
        """Check if this parser can handle the source (extension or MIME)."""
        return False
