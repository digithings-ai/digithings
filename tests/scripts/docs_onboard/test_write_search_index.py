from __future__ import annotations

from pathlib import Path
from typing import Any  # score:allow untyped any — captured POST /ingest payloads

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
    assert posted[0]["doc_type"] == "html"
    assert posted[1]["doc_type"] == "pdf"
    assert posted[1]["metadata"]["page_class"] == "pdf"
