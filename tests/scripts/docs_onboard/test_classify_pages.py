from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.classify_pages import classify_pages
from scripts.docs_onboard.models import DiscoveredPage, OnboardManifest, PageClass
from scripts.docs_onboard.workspace import Workspace

pytestmark = pytest.mark.unit


def test_classify_prefers_docs_and_pdfs(tmp_path: Path) -> None:
    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        docs_path_prefixes=("/guide",),
        skip_path_prefixes=("/blog",),
    )
    ws = Workspace.create(tmp_path / "work")
    for url, ctype in [
        ("https://docs.example.com/guide/start", "text/html"),
        ("https://docs.example.com/blog/news", "text/html"),
        ("https://docs.example.com/files/manual.pdf", "application/pdf"),
    ]:
        ws.append_page(
            DiscoveredPage(
                url=url,
                final_url=url,
                content_type=ctype,
                depth=1,
            )
        )
    classify_pages(manifest, ws)
    by_url = {c.page.url: c for c in ws.iter_classified()}
    assert by_url["https://docs.example.com/guide/start"].page_class == PageClass.docs
    assert by_url["https://docs.example.com/blog/news"].page_class == PageClass.skip
    assert by_url["https://docs.example.com/files/manual.pdf"].page_class == PageClass.pdf
