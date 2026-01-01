"""Workdir layout helpers for the docs_onboard pipeline."""

from __future__ import annotations

import json
from collections.abc import Iterator
from pathlib import Path

from scripts.docs_onboard.models import ClassifiedPage, DiscoveredPage, SourceMapEntry


class Workspace:
    """Filesystem layout for one onboard run.

    Layout::

        <root>/
          pages.jsonl
          classified.jsonl
          assets/
          html/
          search_md/   # HTML→markdown sidecars for digisearch ingest (#2191)
          meta/source_map.jsonl
    """

    def __init__(self, root: Path) -> None:
        self.root = Path(root).resolve()
        self.pages_path = self.root / "pages.jsonl"
        self.classified_path = self.root / "classified.jsonl"
        self.assets_dir = self.root / "assets"
        self.html_dir = self.root / "html"
        self.search_md_dir = self.root / "search_md"
        self.meta_dir = self.root / "meta"
        self.source_map_path = self.meta_dir / "source_map.jsonl"

    @classmethod
    def create(cls, root: Path) -> Workspace:
        """Create the workdir tree and return a :class:`Workspace`."""
        ws = cls(root)
        ws.root.mkdir(parents=True, exist_ok=True)
        ws.assets_dir.mkdir(parents=True, exist_ok=True)
        ws.html_dir.mkdir(parents=True, exist_ok=True)
        ws.search_md_dir.mkdir(parents=True, exist_ok=True)
        ws.meta_dir.mkdir(parents=True, exist_ok=True)
        return ws

    def append_page(self, page: DiscoveredPage) -> None:
        """Append one discovered page as a JSONL line."""
        self._append_jsonl(self.pages_path, page.model_dump(mode="json"))

    def iter_pages(self) -> Iterator[DiscoveredPage]:
        """Yield discovered pages from ``pages.jsonl``."""
        for obj in self._iter_jsonl(self.pages_path):
            yield DiscoveredPage.model_validate(obj)

    def clear_pages(self) -> None:
        """Truncate ``pages.jsonl`` (e.g. before a fresh scrape)."""
        self.pages_path.write_text("", encoding="utf-8")

    def append_classified(self, page: ClassifiedPage) -> None:
        """Append one classified page as a JSONL line."""
        self._append_jsonl(self.classified_path, page.model_dump(mode="json"))

    def clear_classified(self) -> None:
        """Truncate ``classified.jsonl``."""
        self.classified_path.write_text("", encoding="utf-8")

    def iter_classified(self) -> Iterator[ClassifiedPage]:
        """Yield classified pages from ``classified.jsonl``."""
        for obj in self._iter_jsonl(self.classified_path):
            yield ClassifiedPage.model_validate(obj)

    def append_source_map(self, entry: SourceMapEntry) -> None:
        """Append a local↔URL mapping row."""
        self._append_jsonl(self.source_map_path, entry.model_dump(mode="json"))

    def iter_source_map(self) -> Iterator[SourceMapEntry]:
        """Yield source-map entries."""
        for obj in self._iter_jsonl(self.source_map_path):
            yield SourceMapEntry.model_validate(obj)

    @staticmethod
    def _append_jsonl(path: Path, obj: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        with path.open("a", encoding="utf-8") as fh:
            fh.write(json.dumps(obj, ensure_ascii=False) + "\n")

    @staticmethod
    def _iter_jsonl(path: Path) -> Iterator[dict]:
        if not path.is_file():
            return
        with path.open(encoding="utf-8") as fh:
            for line in fh:
                line = line.strip()
                if not line:
                    continue
                yield json.loads(line)
