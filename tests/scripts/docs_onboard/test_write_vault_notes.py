from __future__ import annotations

from pathlib import Path
from typing import Any  # score:allow untyped any — NoteWriter test double records open dicts
from unittest import mock

import pytest
from digivault.frontmatter import split_frontmatter
from digivault.vault import Vault

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
    SourceMapEntry,
)
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace
from scripts.docs_onboard.write_vault_notes import write_vault_notes

pytestmark = pytest.mark.unit


class _RecordingWriter:
    """NoteWriter double that records every write_note call."""

    def __init__(self) -> None:
        self.calls: list[dict[str, Any]] = []

    def write_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        self.calls.append(
            {
                "name": name,
                "frontmatter": dict(frontmatter or {}),
                "body": body,
                "subdir": subdir,
                "overwrite": overwrite,
            }
        )
        return {"ok": True}

    def prune_children(self, parent_doc: str, keep_names: set[str], subdir: str = "") -> list[str]:
        return []


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


def test_multi_segment_pdf_writes_children_and_hub(tmp_path: Path) -> None:
    from digisearch.core.models import Document as DsDocument
    from digisearch.core.models import Segment

    ws = Workspace.create(tmp_path / "work")
    pdf_path = ws.root / "assets" / "guide.pdf"
    pdf_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_path.write_bytes(b"%PDF-fake")
    ws.append_source_map(
        SourceMapEntry(
            local_path="assets/guide.pdf",
            source_url="https://example.com/guide.pdf",
            content_type="application/pdf",
        )
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="https://example.com/guide.pdf",
                final_url="https://example.com/guide.pdf",
                content_type="application/pdf",
                title="Guide",
                depth=0,
                discovered_from="seed",
            ),
            page_class=PageClass.pdf,
            score=100.0,
            reasons=("pdf",),
        )
    )

    parsed = DsDocument(
        id="x",
        content="page one\npage two",
        source=str(pdf_path),
        doc_type="pdf",
        segments=[
            Segment(index=0, label="page:1", text="page one", metadata={"page": 1}),
            Segment(index=1, label="page:2", text="page two", metadata={"page": 2}),
        ],
    )
    monkey_target = "scripts.docs_onboard.write_vault_notes._pdf_document"
    with mock.patch(monkey_target, return_value=parsed):
        writer = _RecordingWriter()
        manifest = OnboardManifest(
            client="acme", seed_url="https://example.com/", vault_subdir="clients/acme"
        )
        count = write_vault_notes(manifest, ws, writer)

    assert count == 3
    names = [call["name"] for call in writer.calls]
    hub = slug_for_url("https://example.com/guide.pdf")
    assert names == [f"{hub}__p001", f"{hub}__p002", hub]
    hub_call = writer.calls[-1]
    assert f"[[{hub}__p001]]" in hub_call["body"]
    assert f"[[{hub}__p002]]" in hub_call["body"]
    assert hub_call["frontmatter"]["segment_count"] == 2
    child = writer.calls[0]
    assert child["body"] == "page one\n"
    assert child["frontmatter"]["segment_label"] == "page:1"
    assert child["frontmatter"]["segment_index"] == 0
    assert child["frontmatter"]["parent_doc"] == hub


def test_duplicate_sibling_headings_produce_distinct_notes(tmp_path: Path) -> None:
    """Two ``## Notes`` sections under the same H1 must not overwrite each other."""
    ws = Workspace.create(tmp_path / "work")
    local = ws.root / "files" / "guide.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text(
        "# Title\n"
        "## Notes\n"
        "First section notes with unique content ALPHA.\n"
        "## Details\n"
        "Some details BETA.\n"
        "## Notes\n"
        "Second section notes with unique content GAMMA.\n",
        encoding="utf-8",
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="repo://acme/guide.md",
                final_url="repo://acme/guide.md",
                content_type="text/markdown",
                title="Guide",
                depth=0,
                local_path="files/guide.md",
                discovered_from="repo_source",
            ),
            page_class=PageClass.repo_doc,
            score=90.0,
            reasons=("repo",),
        )
    )
    writer = _RecordingWriter()
    manifest = OnboardManifest(
        client="acme", seed_url="https://example.com/", vault_subdir="clients/acme"
    )
    count = write_vault_notes(manifest, ws, writer)

    names = [call["name"] for call in writer.calls]
    assert count == len(writer.calls)
    assert len(set(names)) == len(names), f"collided note names: {names}"

    bodies_by_name = {call["name"]: call["body"] for call in writer.calls}
    alpha_notes = [name for name, body in bodies_by_name.items() if "ALPHA" in body]
    gamma_notes = [name for name, body in bodies_by_name.items() if "GAMMA" in body]
    assert len(alpha_notes) == 1
    assert len(gamma_notes) == 1
    assert alpha_notes != gamma_notes

    hub_call = writer.calls[-1]
    child_names = names[:-1]
    for child_name in child_names:
        assert f"[[{child_name}]]" in hub_call["body"]

    # Minor fix: display title strips the "heading:" prefix but segment_label keeps it.
    alpha_call = next(call for call in writer.calls if "ALPHA" in call["body"])
    assert alpha_call["frontmatter"]["segment_label"].startswith("heading:")
    assert "heading:" not in alpha_call["frontmatter"]["title"]


def test_long_shared_prefix_headings_produce_distinct_notes(tmp_path: Path) -> None:
    """Two headings whose slugs collide after 48-char truncation must not overwrite."""
    ws = Workspace.create(tmp_path / "work")
    local = ws.root / "files" / "longheadings.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    heading_one = "This Is A Very Long Heading Title That Goes On For Section Part One"
    heading_two = "This Is A Very Long Heading Title That Goes On For Section Part Two"
    local.write_text(
        f"# Title\n## {heading_one}\nUnique content ONE.\n## {heading_two}\nUnique content TWO.\n",
        encoding="utf-8",
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="repo://acme/longheadings.md",
                final_url="repo://acme/longheadings.md",
                content_type="text/markdown",
                title="Guide",
                depth=0,
                local_path="files/longheadings.md",
                discovered_from="repo_source",
            ),
            page_class=PageClass.repo_doc,
            score=90.0,
            reasons=("repo",),
        )
    )
    writer = _RecordingWriter()
    manifest = OnboardManifest(
        client="acme", seed_url="https://example.com/", vault_subdir="clients/acme"
    )
    count = write_vault_notes(manifest, ws, writer)

    names = [call["name"] for call in writer.calls]
    assert count == len(writer.calls)
    assert len(set(names)) == len(names), f"collided note names: {names}"

    bodies_by_name = {call["name"]: call["body"] for call in writer.calls}
    one_notes = [name for name, body in bodies_by_name.items() if "ONE" in body]
    two_notes = [name for name, body in bodies_by_name.items() if "TWO" in body]
    assert len(one_notes) == 1
    assert len(two_notes) == 1
    assert one_notes != two_notes


def test_single_segment_document_writes_one_note(tmp_path: Path) -> None:
    ws = Workspace.create(tmp_path / "work")
    local = ws.root / "files" / "readme.md"
    local.parent.mkdir(parents=True, exist_ok=True)
    local.write_text("# Readme\n\nJust one section.\n", encoding="utf-8")
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url="repo://acme/README.md",
                final_url="repo://acme/README.md",
                content_type="text/markdown",
                title="Readme",
                depth=0,
                local_path="files/readme.md",
                discovered_from="repo_source",
            ),
            page_class=PageClass.repo_doc,
            score=90.0,
            reasons=("repo",),
        )
    )
    writer = _RecordingWriter()
    manifest = OnboardManifest(
        client="acme", seed_url="https://example.com/", vault_subdir="clients/acme"
    )
    count = write_vault_notes(manifest, ws, writer)
    assert count == 1
    assert "__" not in writer.calls[0]["name"]
    assert "segment_label" not in writer.calls[0]["frontmatter"]


def test_reingest_prunes_stale_children_after_section_is_inserted(tmp_path: Path) -> None:
    """A changed segment layout must replace, not accumulate, child notes."""
    manifest = OnboardManifest(
        client="acme", seed_url="https://example.com/", vault_subdir="clients/acme"
    )
    ws = Workspace.create(tmp_path / "work")
    url = "repo://acme/guide.md"
    local = ws.root / "files" / "guide.md"
    local.parent.mkdir(parents=True)
    local.write_text(
        "# Guide\n## Notes\nAlpha\n## Notes\nBravo\n## Tail\nCharlie\n",
        encoding="utf-8",
    )
    ws.append_classified(
        ClassifiedPage(
            page=DiscoveredPage(
                url=url,
                final_url=url,
                content_type="text/markdown",
                title="Guide",
                depth=0,
                local_path="files/guide.md",
                discovered_from="repo_source",
            ),
            page_class=PageClass.repo_doc,
            score=90.0,
            reasons=("repo",),
        )
    )
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    vault = Vault(vault_root)
    write_vault_notes(manifest, ws, vault)

    local.write_text(
        "# Guide\n## Intro\nNew\n## Notes\nAlpha\n## Notes\nBravo\n## Tail\nCharlie\n",
        encoding="utf-8",
    )
    write_vault_notes(manifest, ws, vault)

    slug = slug_for_url(url)
    assert {note.name for note in vault.list_notes()} == {
        slug,
        f"{slug}__guide-intro",
        f"{slug}__guide-notes-i001",
        f"{slug}__guide-notes-i002",
        f"{slug}__guide-tail",
    }
