"""ParserRegistry - auto-select parser by extension or MIME."""

from __future__ import annotations

from pathlib import Path

from digisearch.core.models import Document
from digisearch.ingestion.base import Parser
from digisearch.ingestion.parsers.plaintext import PlainTextParser


def _default_parsers() -> list[Parser]:
    parsers: list[Parser] = []
    try:
        from digisearch.ingestion.parsers.pdf import PDFParser
        parsers.append(PDFParser())
    except ImportError:
        pass
    try:
        from digisearch.ingestion.parsers.docx import DocxParser
        parsers.append(DocxParser())
    except ImportError:
        pass
    try:
        from digisearch.ingestion.parsers.html import HTMLParser
        parsers.append(HTMLParser())
    except ImportError:
        pass
    try:
        from digisearch.ingestion.parsers.markdown import MarkdownParser
        parsers.append(MarkdownParser())
    except ImportError:
        pass
    try:
        from digisearch.ingestion.parsers.csv import CSVParser
        parsers.append(CSVParser())
    except ImportError:
        pass
    parsers.append(PlainTextParser())
    return parsers


class ParserRegistry:
    """Registry of parsers. Auto-selects by extension."""

    def __init__(self) -> None:
        self._parsers = _default_parsers()

    def get_parser(self, source: str | Path) -> Parser | None:
        """Get parser that can handle source."""
        src = str(source)
        for p in self._parsers:
            if p.can_parse(src):
                return p
        return None

    def parse(self, source: str | Path | bytes) -> Document:
        """Parse source. Uses first matching parser."""
        if isinstance(source, bytes):
            src_str = "<bytes>"
        else:
            src_str = str(source)
        parser = self.get_parser(src_str)
        if parser:
            return parser.parse(source)
        return PlainTextParser().parse(source)
