from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.models import DiscoveredPage
from scripts.docs_onboard.workspace import Workspace

pytestmark = pytest.mark.unit


def test_workspace_append_pages(tmp_path: Path) -> None:
    ws = Workspace.create(tmp_path / "work")
    page = DiscoveredPage(
        url="https://docs.example.com/guide",
        final_url="https://docs.example.com/guide",
        content_type="text/html",
        title="Guide",
        depth=1,
    )
    ws.append_page(page)
    loaded = list(ws.iter_pages())
    assert len(loaded) == 1
    assert loaded[0].url.endswith("/guide")
    assert ws.assets_dir.is_dir()
    assert ws.html_dir.is_dir()
    assert ws.search_md_dir.is_dir()
    assert ws.meta_dir.is_dir()
