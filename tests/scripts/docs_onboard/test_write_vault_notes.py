from __future__ import annotations

from pathlib import Path

import pytest
from digivault.frontmatter import split_frontmatter
from digivault.vault import Vault

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
)
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace
from scripts.docs_onboard.write_vault_notes import write_vault_notes

pytestmark = pytest.mark.unit


def test_slug_for_url_stable() -> None:
    assert slug_for_url("https://docs.example.com/guides/Start/") == slug_for_url(
        "https://docs.example.com/guides/Start"
    )
    assert "/" not in slug_for_url("https://docs.example.com/a/b")


def test_write_vault_notes_html_includes_source_url(tmp_path: Path) -> None:
    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        vault_subdir="clients/example",
    )
    ws = Workspace.create(tmp_path / "work")
    url = "https://docs.example.com/guide/start"
    html_rel = "html/guide-start.html"
    (ws.html_dir / "guide-start.html").write_text(
        "<html><title>Start</title><body><main>Ship agents safely</main></body></html>",
        encoding="utf-8",
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
    # A skip page must not produce a note
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="https://docs.example.com/blog/news",
                final_url="https://docs.example.com/blog/news",
                content_type="text/html",
                title="News",
                depth=1,
                html_path="html/blog.html",
            ),
            page_class=PageClass.skip,
            score=0.0,
            reasons=("skip_prefix:/blog",),
        )
    )
    (ws.html_dir / "blog.html").write_text("<html><body>noise</body></html>", encoding="utf-8")

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    n = write_vault_notes(manifest, ws, vault)
    assert n == 1
    notes = vault.list_notes()
    assert len(notes) == 1
    raw = vault.read_text(notes[0].name)
    fm, body = split_frontmatter(raw)
    assert fm.get("source_url") == url
    assert "Ship agents safely" in body
    assert "client:example" in (fm.get("tags") or [])


def test_write_vault_notes_normalizes_digi_product_title(tmp_path: Path) -> None:
    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        vault_subdir="clients/example",
    )
    ws = Workspace.create(tmp_path / "work")
    url = "https://docs.example.com/modules/digigraph"
    html_rel = "html/digigraph.html"
    (ws.html_dir / "digigraph.html").write_text(
        "<html><title>DigiGraph</title><body><main>Orchestration brain</main></body></html>",
        encoding="utf-8",
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url=url,
                final_url=url,
                content_type="text/html",
                title="DigiGraph",
                depth=1,
                html_path=html_rel,
            ),
            page_class=PageClass.docs,
            score=80.0,
            reasons=("docs_prefix:/modules",),
        )
    )
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    n = write_vault_notes(manifest, ws, vault)
    assert n == 1
    notes = vault.list_notes()
    raw = vault.read_text(notes[0].name)
    fm, _ = split_frontmatter(raw)
    assert fm.get("title") == "digigraph"
