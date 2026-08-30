from __future__ import annotations

from pathlib import Path

import pytest

from scripts.docs_onboard.ingest_openapi import ingest_openapi_sources, openapi_to_markdown
from scripts.docs_onboard.ingest_repo import ingest_repo_docs
from scripts.docs_onboard.ingest_static import ingest_static_sources, resolve_globs
from scripts.docs_onboard.models import (
    OnboardManifest,
    PageClass,
    RepoSource,
    load_manifest,
)
from scripts.docs_onboard.run_onboard import run_onboard
from scripts.docs_onboard.workspace import Workspace
from scripts.docs_onboard.write_search_index import write_search_index
from scripts.docs_onboard.write_vault_notes import DigivaultApiWriter, write_vault_notes

pytestmark = pytest.mark.unit


def test_digithings_manifest_loads() -> None:
    repo = Path(__file__).resolve().parents[3]
    path = repo / "docs" / "projects" / "digithings" / "onboard.yaml"
    m = load_manifest(path)
    assert m.client == "digithings"
    assert "vault" in m.sinks and "search" in m.sinks
    assert "digiquant.io" in m.allowed_hosts
    assert m.static_sources
    assert m.openapi_sources
    assert m.repo_source is not None
    assert m.repo_source.kind == "local"


def test_page_class_openapi_and_repo_doc() -> None:
    assert PageClass.openapi.value == "openapi"
    assert PageClass.repo_doc.value == "repo_doc"


def test_resolve_globs_and_static_ingest(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    target = repo / "docs" / "ARCHITECTURE.md"
    target.write_text("# Arch\n\nHello vault.\n", encoding="utf-8")
    globs_yaml = repo / "globs.yaml"
    globs_yaml.write_text("globs:\n  - docs/ARCHITECTURE.md\n", encoding="utf-8")
    paths = resolve_globs(repo, ("docs/ARCHITECTURE.md",))
    assert target.resolve() in paths

    manifest = OnboardManifest(
        client="t",
        seed_url="https://example.com/",
        static_sources=str(globs_yaml),
    )
    ws = Workspace.create(tmp_path / "work")
    n = ingest_static_sources(manifest, ws, repo_root=repo)
    assert n == 1
    classified = list(ws.iter_classified())
    assert classified[0].page_class == PageClass.repo_doc
    assert classified[0].page.local_path


def test_openapi_ingest_and_markdown(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    spec_dir = repo / "docs" / "openapi"
    spec_dir.mkdir(parents=True)
    spec = spec_dir / "digigraph.json"
    spec.write_text(
        '{"openapi":"3.0.0","info":{"title":"digigraph","version":"1.0"},'
        '"paths":{"/healthz":{"get":{}}}}',
        encoding="utf-8",
    )
    cfg = repo / "openapi.yaml"
    cfg.write_text(
        "files:\n  - docs/openapi/digigraph.json\nkinds: [openapi]\n"
        "vault_note_type: api_reference\n",
        encoding="utf-8",
    )
    md = openapi_to_markdown(spec, note_type="api_reference")
    assert "digigraph" in md
    assert "/healthz" in md

    manifest = OnboardManifest(
        client="t",
        seed_url="https://example.com/",
        openapi_sources=str(cfg),
    )
    ws = Workspace.create(tmp_path / "work")
    n = ingest_openapi_sources(manifest, ws, repo_root=repo)
    assert n == 1
    assert list(ws.iter_classified())[0].page_class == PageClass.openapi


def test_repo_source_local_lists_architecture(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    manifest = OnboardManifest(
        client="digithings",
        seed_url="https://digithings.ai/",
        repo_source=RepoSource(
            kind="local",
            path=".",
            globs=("digigraph/ARCHITECTURE.md",),
        ),
    )
    ws = Workspace.create(tmp_path / "work")
    n = ingest_repo_docs(manifest, ws, repo_root=repo)
    assert n == 1
    urls = [c.page.url for c in ws.iter_classified()]
    assert any("digigraph/ARCHITECTURE.md" in u for u in urls)


def test_dry_run_digithings_skip_crawl(tmp_path: Path) -> None:
    repo = Path(__file__).resolve().parents[3]
    manifest = load_manifest(repo / "docs/projects/digithings/onboard.yaml")
    # Narrow globs for speed in CI
    manifest = manifest.model_copy(
        update={
            "repo_source": RepoSource(
                kind="local",
                path=".",
                globs=(
                    "digigraph/ARCHITECTURE.md",
                    "docs/openapi/digigraph.json",
                ),
            ),
            "static_sources": None,
            "openapi_sources": str(repo / "docs/projects/digithings/sources/openapi.yaml"),
        }
    )
    ws = Workspace.create(tmp_path / "work")
    result = run_onboard(
        manifest,
        ws,
        repo_root=repo,
        dry_run=True,
        skip_crawl=True,
    )
    assert result.dry_run is True
    assert result.errors == ()
    assert result.openapi_files >= 1
    assert result.repo_files >= 1
    assert result.docs_kept >= 2
    classes = {c.page_class for c in ws.iter_classified()}
    assert PageClass.openapi in classes
    assert PageClass.repo_doc in classes


def test_vault_and_search_sinks_for_repo_doc(tmp_path: Path) -> None:
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "ARCHITECTURE.md").write_text(
        "# Component\n\nOrchestrates graphs.\n", encoding="utf-8"
    )
    manifest = OnboardManifest(
        client="t",
        seed_url="https://example.com/",
        sinks=("vault", "search"),
        digisearch_index="t_docs",
        vault_subdir="clients/t",
        repo_source=RepoSource(kind="local", path=".", globs=("docs/ARCHITECTURE.md",)),
    )
    ws = Workspace.create(tmp_path / "work")
    assert ingest_repo_docs(manifest, ws, repo_root=repo) == 1

    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    from digivault.vault import Vault

    n = write_vault_notes(manifest, ws, Vault(vault_root))
    assert n == 1
    bodies = " ".join(
        Vault(vault_root).read_text(note.name) for note in Vault(vault_root).list_notes()
    )
    assert "Orchestrates graphs" in bodies

    posted: list[dict] = []

    def post_ingest(payload: dict) -> dict:
        posted.append(payload)
        return {"status": "ok"}

    s = write_search_index(manifest, ws, post_ingest=post_ingest)
    assert s == 1
    assert posted[0]["index_name"] == "t_docs"
    assert posted[0]["metadata"]["page_class"] == "repo_doc"


def test_digivault_api_writer_posts_overwrite(tmp_path: Path) -> None:
    seen: list[dict] = []

    def post_json(url: str, payload: dict, headers: dict) -> dict:
        seen.append({"url": url, "payload": payload, "headers": headers})
        return {"name": payload["name"]}

    writer = DigivaultApiWriter("http://digivault:8004", bearer_token="tok", post_json=post_json)
    writer.write_note(
        "n1",
        frontmatter={"title": "T", "tags": ["onboard"]},
        body="body\n",
        subdir="clients/t",
        overwrite=True,
    )
    assert seen[0]["url"].endswith("/v1/notes")
    assert seen[0]["payload"]["overwrite"] is True
    assert seen[0]["headers"]["Authorization"] == "Bearer tok"


def test_digivault_api_writer_batches_upserts() -> None:
    seen: list[dict] = []

    def post_json(url: str, payload: dict, headers: dict) -> dict:
        seen.append({"url": url, "payload": payload, "headers": headers})
        return {"notes": payload["notes"]}

    writer = DigivaultApiWriter("http://digivault:8004", post_json=post_json)
    writer.begin_batch()
    writer.write_note("a", body="links to [[b]]\n", overwrite=True)
    writer.write_note("b", body="links to [[a]]\n", overwrite=True)
    writer.flush()

    assert len(seen) == 1
    assert seen[0]["url"].endswith("/v1/notes/batch")
    assert [note["name"] for note in seen[0]["payload"]["notes"]] == ["a", "b"]
