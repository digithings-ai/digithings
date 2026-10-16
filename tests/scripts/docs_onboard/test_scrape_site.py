from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.models import OnboardManifest
from scripts.docs_onboard.scrape_site import scrape_site
from scripts.docs_onboard.workspace import Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "sample_docs_index.html"

pytestmark = pytest.mark.unit


def test_scrape_site_bfs_respects_caps(tmp_path: Path) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    pages = {
        "https://docs.example.com/": html,
        "https://docs.example.com/guide/start": (
            "<html><title>Start</title><body><main>Hello</main></body></html>"
        ),
        "https://docs.example.com/blog/news": (
            "<html><title>News</title><body>skip me</body></html>"
        ),
    }

    def fetch_html(url: str) -> tuple[str, str, str]:
        return url, "text/html", pages[url]

    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        allowed_hosts=("docs.example.com",),
        max_pages=10,
        max_depth=2,
    )
    ws = Workspace.create(tmp_path / "work")
    n = scrape_site(manifest, ws, fetch_html=fetch_html)
    urls = {p.url for p in ws.iter_pages()}
    assert n >= 2
    assert "https://docs.example.com/guide/start" in urls
    assert "https://docs.example.com/files/manual.pdf" in urls
    pdf = next(p for p in ws.iter_pages() if p.url.endswith(".pdf"))
    assert pdf.content_type == "application/pdf"
    start = next(p for p in ws.iter_pages() if p.url.endswith("/guide/start"))
    assert start.html_path is not None
    assert (ws.root / start.html_path).is_file()
