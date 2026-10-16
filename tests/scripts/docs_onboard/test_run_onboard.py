from __future__ import annotations

from pathlib import Path
from typing import Any  # score:allow untyped any — monkeypatch / post_ingest test doubles
from unittest.mock import MagicMock

import pytest

from scripts.docs_onboard.models import OnboardManifest, PageClass
from scripts.docs_onboard.run_onboard import run_onboard
from scripts.docs_onboard.workspace import Workspace

FIXTURE = Path(__file__).parent / "fixtures" / "sample_docs_index.html"

pytestmark = pytest.mark.unit


def test_run_onboard_order_and_skips_vault_noise(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    html = FIXTURE.read_text(encoding="utf-8")
    pages = {
        "https://docs.example.com/": html,
        "https://docs.example.com/guide/start": (
            "<html><title>Start</title><body><main>Hello docs</main></body></html>"
        ),
        "https://docs.example.com/blog/news": (
            "<html><title>News</title><body>skip me</body></html>"
        ),
    }

    def fetch_html(url: str) -> tuple[str, str, str]:
        return url, "text/html", pages[url]

    def download(url: str) -> bytes:
        assert url.endswith(".pdf")
        return b"%PDF-1.4 onboard"

    calls: list[str] = []
    real_scrape = __import__(
        "scripts.docs_onboard.scrape_site", fromlist=["scrape_site"]
    ).scrape_site
    real_classify = __import__(
        "scripts.docs_onboard.classify_pages", fromlist=["classify_pages"]
    ).classify_pages
    real_fetch = __import__("scripts.docs_onboard.fetch_docs", fromlist=["fetch_docs"]).fetch_docs
    real_vault = __import__(
        "scripts.docs_onboard.write_vault_notes", fromlist=["write_vault_notes"]
    ).write_vault_notes

    def wrap_scrape(*a: Any, **k: Any) -> int:
        calls.append("scrape")
        return real_scrape(*a, **k)

    def wrap_classify(*a: Any, **k: Any) -> int:
        calls.append("classify")
        return real_classify(*a, **k)

    def wrap_fetch(*a: Any, **k: Any) -> int:
        calls.append("fetch")
        return real_fetch(*a, **k)

    def wrap_vault(*a: Any, **k: Any) -> int:
        calls.append("vault")
        return real_vault(*a, **k)

    monkeypatch.setattr("scripts.docs_onboard.run_onboard.scrape_site", wrap_scrape)
    monkeypatch.setattr("scripts.docs_onboard.run_onboard.classify_pages", wrap_classify)
    monkeypatch.setattr("scripts.docs_onboard.run_onboard.fetch_docs", wrap_fetch)
    monkeypatch.setattr("scripts.docs_onboard.run_onboard.write_vault_notes", wrap_vault)

    posted: list[dict[str, Any]] = []

    def post_ingest(payload: dict[str, Any]) -> dict[str, Any]:
        calls.append("search")
        posted.append(payload)
        return {"status": "ok", "doc_id": "1", "chunks_created": 1, "index_name": "example_docs"}

    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        allowed_hosts=("docs.example.com",),
        max_pages=10,
        max_depth=2,
        sinks=("vault", "search"),
        digisearch_index="example_docs",
        vault_subdir="clients/example",
        docs_path_prefixes=("/guide",),
        skip_path_prefixes=("/blog",),
    )
    ws = Workspace.create(tmp_path / "work")
    vault_root = tmp_path / "vault"
    vault_root.mkdir()

    result = run_onboard(
        manifest,
        ws,
        vault_root=vault_root,
        fetch_html=fetch_html,
        download=download,
        post_ingest=post_ingest,
    )

    assert calls[:4] == ["scrape", "classify", "fetch", "vault"]
    assert "search" in calls
    assert result.pages_seen >= 2
    assert result.skipped >= 1
    assert result.vault_notes >= 1
    assert result.errors == ()

    # Skip pages never reach vault: only guide note (and maybe docs root) present
    from digivault.vault import Vault

    notes = Vault(vault_root).list_notes()
    bodies = " ".join(Vault(vault_root).read_text(n.name) for n in notes)
    assert "skip me" not in bodies
    assert "Hello docs" in bodies

    # Classified skip must not be posted as search docs for blog
    for payload in posted:
        assert "/blog/" not in payload["metadata"]["source_url"]


def test_run_onboard_vault_only_skips_search(tmp_path: Path) -> None:
    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        allowed_hosts=("docs.example.com",),
        sinks=("vault",),
        docs_path_prefixes=("/guide",),
    )
    ws = Workspace.create(tmp_path / "work")

    def fetch_html(url: str) -> tuple[str, str, str]:
        return (
            url,
            "text/html",
            "<html><title>G</title><body><a href='/guide/x'>x</a></body></html>",
        )

    # Empty crawl beyond seed is fine — ensure search not invoked
    search = MagicMock()
    vault_root = tmp_path / "vault"
    vault_root.mkdir()
    result = run_onboard(
        manifest,
        ws,
        vault_root=vault_root,
        sinks=("vault",),
        fetch_html=fetch_html,
        post_ingest=search,
    )
    search.assert_not_called()
    assert result.search_docs == 0
    assert PageClass.docs  # keep import used / typing sanity


def test_run_onboard_reused_workdir_does_not_accumulate_classified(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
) -> None:
    """Second crawl into the same workdir must not append duplicate classified rows (#2138)."""
    repo = tmp_path / "repo"
    (repo / "docs").mkdir(parents=True)
    (repo / "docs" / "GUIDE.md").write_text("# Guide\n\nBody.\n", encoding="utf-8")
    globs_yaml = repo / "globs.yaml"
    globs_yaml.write_text("globs:\n  - docs/GUIDE.md\n", encoding="utf-8")

    manifest = OnboardManifest(
        client="example",
        seed_url="https://docs.example.com/",
        allowed_hosts=("docs.example.com",),
        max_pages=2,
        max_depth=0,
        static_sources=str(globs_yaml),
        docs_path_prefixes=("/",),
    )

    def fetch_html(url: str) -> tuple[str, str, str]:
        return (
            url,
            "text/html",
            "<html><title>Seed</title><body><main>Seed page</main></body></html>",
        )

    workdir = tmp_path / "work"
    ws = Workspace.create(workdir)

    first = run_onboard(
        manifest,
        ws,
        repo_root=repo,
        fetch_html=fetch_html,
        sinks=(),
        dry_run=True,
    )
    assert first.errors == ()
    count_after_first = sum(1 for _ in ws.iter_classified())
    assert count_after_first >= 2  # crawl + static

    second = run_onboard(
        manifest,
        ws,
        repo_root=repo,
        fetch_html=fetch_html,
        sinks=(),
        dry_run=True,
    )
    assert second.errors == ()
    count_after_second = sum(1 for _ in ws.iter_classified())
    assert count_after_second == count_after_first
    assert second.docs_kept == first.docs_kept
