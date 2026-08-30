from __future__ import annotations

from pathlib import Path
from typing import Any  # score:allow untyped any — captured POST /ingest payloads

import pytest
from digisearch.ingestion.parsers.markdown import MarkdownParser
from digisearch.ingestion.segmenters.heading import heading_segments

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
    SourceMapEntry,
)
from scripts.docs_onboard.workspace import Workspace
from scripts.docs_onboard.write_search_index import write_search_index

pytestmark = pytest.mark.unit


def test_write_search_index_posts_metadata(tmp_path: Path) -> None:
    posted: list[dict[str, Any]] = []

    def post_ingest(payload: dict[str, Any]) -> dict[str, Any]:
        posted.append(payload)
        return {
            "doc_id": "x",
            "chunks_created": 1,
            "index_name": payload["index_name"],
            "status": "ok",
        }

    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        digisearch_index="example_docs",
    )
    ws = Workspace.create(tmp_path / "work")
    url = "https://docs.example.com/guide/start"
    html_rel = "html/guide-start.html"
    (ws.html_dir / "guide-start.html").write_text(
        "<html><body>docs body</body></html>", encoding="utf-8"
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url=url,
                final_url=url,
                content_type="text/html",
                title="Start",
                depth=1,
                html_path=html_rel,
            ),
            page_class=PageClass.docs,
            score=80.0,
            reasons=("docs_prefix:/guide",),
        )
    )
    ws.append_source_map(
        SourceMapEntry(
            local_path="assets/manual.pdf",
            source_url="https://docs.example.com/files/manual.pdf",
            content_type="application/pdf",
        )
    )
    (ws.assets_dir / "manual.pdf").write_bytes(b"%PDF-1.4")

    n = write_search_index(manifest, ws, post_ingest=post_ingest)
    assert n == 2
    assert posted[0]["metadata"]["source_url"].startswith("https://")
    assert posted[0]["index_name"] == "example_docs"
    # Crawled HTML is converted to markdown before ingest (#2191).
    assert posted[0]["doc_type"] == "markdown"
    assert posted[0]["source"].endswith("search_md/html/guide-start.md")
    assert Path(posted[0]["source"]).is_file()
    assert posted[1]["doc_type"] == "pdf"
    assert posted[1]["metadata"]["page_class"] == "pdf"


def test_crawled_html_search_path_preserves_heading_segments(tmp_path: Path) -> None:
    """Multi-<h2> crawl HTML must reach digisearch as segmented markdown (#2191)."""
    posted: list[dict[str, Any]] = []

    def post_ingest(payload: dict[str, Any]) -> dict[str, Any]:
        posted.append(payload)
        return {
            "doc_id": "seg",
            "chunks_created": 3,
            "index_name": payload["index_name"],
            "status": "ok",
        }

    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        digisearch_index="example_docs",
    )
    ws = Workspace.create(tmp_path / "work")
    url = "https://docs.example.com/guide/sections"
    html_rel = "html/sections.html"
    (ws.html_dir / "sections.html").write_text(
        """<!DOCTYPE html><html><body>
        <h1>Guide</h1>
        <h2>Alpha</h2><p>alpha body</p>
        <h2>Bravo</h2><p>bravo body</p>
        <h2>Charlie</h2><p>charlie body</p>
        </body></html>""",
        encoding="utf-8",
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url=url,
                final_url=url,
                content_type="text/html",
                title="Sections",
                depth=1,
                html_path=html_rel,
            ),
            page_class=PageClass.docs,
            score=90.0,
            reasons=("docs_prefix:/guide",),
        )
    )

    n = write_search_index(manifest, ws, post_ingest=post_ingest)
    assert n == 1
    assert posted[0]["doc_type"] == "markdown"
    md_path = Path(posted[0]["source"])
    assert md_path.is_file()
    body = md_path.read_text(encoding="utf-8")
    labels = [s.label for s in heading_segments(body)]
    assert any("Alpha" in label for label in labels)
    assert any("Bravo" in label for label in labels)
    assert any("Charlie" in label for label in labels)

    doc = MarkdownParser().parse(md_path)
    assert doc.doc_type == "markdown"
    assert doc.segments
    assert all(seg.label for seg in doc.segments)
    # SegmentAwareChunker reads segment.label into chunk metadata as segment_label.
    assert {seg.label for seg in doc.segments} == set(labels)


def test_markdown_repo_doc_unchanged(tmp_path: Path) -> None:
    posted: list[dict[str, Any]] = []

    def post_ingest(payload: dict[str, Any]) -> dict[str, Any]:
        posted.append(payload)
        return {"doc_id": "m", "chunks_created": 1, "index_name": "x", "status": "ok"}

    manifest = OnboardManifest(
        client="example",
        seed_url="https://example.com/",
        digisearch_index="example_docs",
    )
    ws = Workspace.create(tmp_path / "work")
    md_rel = "assets/readme.md"
    (ws.assets_dir / "readme.md").write_text("# Title\n\n## Section\n\nbody\n", encoding="utf-8")
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="https://example.com/readme",
                final_url="https://example.com/readme",
                content_type="text/markdown",
                title="Readme",
                depth=0,
                local_path=md_rel,
            ),
            page_class=PageClass.repo_doc,
            score=100.0,
            reasons=("repo",),
        )
    )
    n = write_search_index(manifest, ws, post_ingest=post_ingest)
    assert n == 1
    assert posted[0]["doc_type"] == "markdown"
    assert posted[0]["source"].endswith("assets/readme.md")
    assert "search_md" not in posted[0]["source"]
