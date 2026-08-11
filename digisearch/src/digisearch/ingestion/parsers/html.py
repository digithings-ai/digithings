"""HTML parser. Uses beautifulsoup4. Strips nav/footer."""

from __future__ import annotations

import uuid
from pathlib import Path

from digisearch.core.models import Document
from digisearch.ingestion.base import Parser

try:
    from bs4 import BeautifulSoup

    _BS4_AVAILABLE = True
except ImportError:
    _BS4_AVAILABLE = False


class HTMLParser(Parser):
    """Parse HTML. Extracts text, strips nav/footer by default."""

    def __init__(self, strip_nav_footer: bool = True) -> None:
        self.strip_nav_footer = strip_nav_footer

    def parse(self, source: str | Path | bytes) -> Document:
        if isinstance(source, bytes):
            raw = source.decode("utf-8", errors="replace")
            src_str = "<bytes>"
        else:
            path = Path(source)
            if path.exists():
                raw = path.read_text(encoding="utf-8", errors="replace")
                src_str = str(path)
            else:
                raw = str(source)
                src_str = "<string>"
        if _BS4_AVAILABLE:
            soup = BeautifulSoup(raw, "html.parser")
            for tag in soup.find_all(["script", "style"]):
                tag.decompose()
            if self.strip_nav_footer:
                for tag in soup.find_all(["nav", "footer", "header"]):
                    tag.decompose()
            content = soup.get_text(separator="\n", strip=True)
        else:
            content = raw
        doc_id = str(uuid.uuid4())
        return Document(
            id=doc_id,
            content=content,
            source=src_str,
            doc_type="html",
            metadata={},
        )

    def can_parse(self, source: str) -> bool:
        ext = Path(source).suffix.lower() if "." in source else ""
        return ext in (".html", ".htm", ".xhtml")
