from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.fetch_docs import fetch_docs
from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
)
from scripts.docs_onboard.workspace import Workspace

pytestmark = pytest.mark.unit


def test_fetch_docs_writes_asset_and_source_map(tmp_path: Path) -> None:
    manifest = OnboardManifest(client="example", seed_url="https://docs.example.com/")
    ws = Workspace.create(tmp_path / "work")
    url = "https://docs.example.com/files/manual.pdf"
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url=url,
                final_url=url,
                content_type="application/pdf",
                depth=1,
            ),
            page_class=PageClass.pdf,
            score=100.0,
            reasons=("pdf_extension_or_type",),
        )
    )
    payload = b"%PDF-1.4 fake content for onboard test"

    def download(u: str) -> bytes:
        assert u == url
        return payload

    n = fetch_docs(manifest, ws, download=download)
    assert n == 1
    entries = list(ws.iter_source_map())
    assert len(entries) == 1
    assert entries[0].source_url == url
    assert entries[0].local_path.startswith("assets/")
    asset = ws.root / entries[0].local_path
    assert asset.is_file()
    assert asset.read_bytes() == payload

    # Idempotent re-run
    n2 = fetch_docs(manifest, ws, download=download)
    assert n2 == 0
    assert len(list(ws.iter_source_map())) == 1
