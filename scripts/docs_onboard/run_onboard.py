#!/usr/bin/env python3
"""Parent orchestrator: scrape → classify → fetch → static/openapi/repo → sinks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any  # score:allow untyped any — ingest JSON payloads are open dicts

from digivault.vault import Vault

from scripts.docs_onboard.classify_pages import classify_pages
from scripts.docs_onboard.fetch_docs import fetch_docs
from scripts.docs_onboard.ingest_openapi import ingest_openapi_sources
from scripts.docs_onboard.ingest_repo import ingest_repo_docs
from scripts.docs_onboard.ingest_static import ingest_static_sources
from scripts.docs_onboard.models import OnboardManifest, OnboardResult, PageClass, load_manifest
from scripts.docs_onboard.scrape_site import scrape_site
from scripts.docs_onboard.workspace import Workspace
from scripts.docs_onboard.write_search_index import write_search_index
from scripts.docs_onboard.write_vault_notes import DigivaultApiWriter, write_vault_notes

_KEEP = frozenset({PageClass.docs, PageClass.pdf, PageClass.openapi, PageClass.repo_doc})


def _workdir_has_crawl_artifacts(workspace: Workspace) -> bool:
    """True when a prior crawl/ingest run left JSONL state in the workdir."""
    for path in (
        workspace.pages_path,
        workspace.classified_path,
        workspace.source_map_path,
    ):
        if path.is_file() and path.stat().st_size > 0:
            return True
    return False


def _reset_crawl_workdir(workspace: Workspace) -> None:
    """Clear crawl + ingest JSONL state so a reused workdir cannot accumulate rows."""
    workspace.clear_pages()
    workspace.clear_classified()
    if workspace.source_map_path.is_file():
        workspace.source_map_path.write_text("", encoding="utf-8")


def _default_repo_root() -> Path:
    # scripts/docs_onboard/run_onboard.py → repo root is parents[2]
    return Path(__file__).resolve().parents[2]


def run_onboard(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    vault_root: Path | None = None,
    digivault_url: str | None = None,
    digivault_token: str = "",
    sinks: tuple[str, ...] | None = None,
    fetch_html: Callable[[str], tuple[str, str, str]] | None = None,
    download: Callable[[str], bytes] | None = None,
    digisearch_url: str = "http://127.0.0.1:8002",
    digikey_url: str = "http://127.0.0.1:8005",
    api_key: str = "",
    source_prefix: str | None = None,
    post_ingest: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
    repo_root: Path | None = None,
    dry_run: bool = False,
    skip_crawl: bool = False,
    github_token: str | None = None,
) -> OnboardResult:
    """Execute the full leaf chain. Skip pages never reach vault/search writers."""
    errors: list[str] = []
    active_sinks = sinks if sinks is not None else manifest.sinks
    root = repo_root or _default_repo_root()

    pages_seen = 0
    if not skip_crawl:
        if _workdir_has_crawl_artifacts(workspace):
            _reset_crawl_workdir(workspace)
        pages_seen = scrape_site(manifest, workspace, fetch_html=fetch_html)
        classify_pages(manifest, workspace)
        try:
            fetch_docs(manifest, workspace, download=download)
        except Exception as exc:
            errors.append(f"fetch_docs: {exc}")
    else:
        # Fresh classified stream for static/openapi/repo-only runs
        workspace.clear_classified()
        workspace.clear_pages()
        if workspace.source_map_path.is_file():
            workspace.source_map_path.write_text("", encoding="utf-8")

    static_files = 0
    openapi_files = 0
    repo_files = 0
    # Avoid double-ingest when static_sources == repo_source.globs_file (dogfood shape).
    skip_static = False
    if (
        manifest.repo_source is not None
        and manifest.static_sources
        and (manifest.repo_source.globs_file or "").strip() == manifest.static_sources.strip()
    ):
        skip_static = True
    try:
        if not skip_static:
            static_files = ingest_static_sources(manifest, workspace, repo_root=root)
    except Exception as exc:
        errors.append(f"ingest_static: {exc}")
    try:
        openapi_files = ingest_openapi_sources(manifest, workspace, repo_root=root)
    except Exception as exc:
        errors.append(f"ingest_openapi: {exc}")
    try:
        repo_files = ingest_repo_docs(
            manifest, workspace, repo_root=root, github_token=github_token
        )
    except Exception as exc:
        errors.append(f"ingest_repo: {exc}")
    if skip_static and repo_files:
        # Report static coverage via repo for dry-run visibility
        static_files = 0

    classified = list(workspace.iter_classified())
    docs_kept = sum(1 for c in classified if c.page_class in _KEEP)
    skipped = sum(1 for c in classified if c.page_class == PageClass.skip)

    if dry_run:
        return OnboardResult(
            pages_seen=pages_seen,
            docs_kept=docs_kept,
            skipped=skipped,
            vault_notes=0,
            search_docs=0,
            static_files=static_files,
            openapi_files=openapi_files,
            repo_files=repo_files,
            dry_run=True,
            errors=tuple(errors),
        )

    vault_notes = 0
    search_docs = 0

    if "vault" in active_sinks:
        url = (digivault_url or manifest.vault_url or "").strip()
        if url:
            try:
                writer = DigivaultApiWriter(url, bearer_token=digivault_token)
                vault_notes = write_vault_notes(manifest, workspace, writer)
            except Exception as exc:
                errors.append(f"write_vault_notes(api): {exc}")
        elif vault_root is None:
            errors.append(
                "vault sink requested but --vault-root / DIGIVAULT_ROOT / "
                "--digivault-url / manifest.vault_url missing"
            )
        else:
            try:
                vault_root.mkdir(parents=True, exist_ok=True)
                vault_notes = write_vault_notes(manifest, workspace, Vault(vault_root))
            except Exception as exc:
                errors.append(f"write_vault_notes: {exc}")

    if "search" in active_sinks:
        try:
            search_docs = write_search_index(
                manifest,
                workspace,
                digisearch_url=digisearch_url,
                digikey_url=digikey_url,
                api_key=api_key,
                source_prefix=source_prefix,
                post_ingest=post_ingest,
            )
        except Exception as exc:
            errors.append(f"write_search_index: {exc}")

    return OnboardResult(
        pages_seen=pages_seen,
        docs_kept=docs_kept,
        skipped=skipped,
        vault_notes=vault_notes,
        search_docs=search_docs,
        static_files=static_files,
        openapi_files=openapi_files,
        repo_files=repo_files,
        dry_run=False,
        errors=tuple(errors),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True, help="Fresh directory per apply run")
    ap.add_argument(
        "--vault-root",
        type=Path,
        default=None,
        help="digivault root (default: DIGIVAULT_ROOT)",
    )
    ap.add_argument(
        "--digivault-url",
        default=os.environ.get("DIGIVAULT_URL", "").strip() or None,
        help="digivault HTTP base for POST /v1/notes upserts",
    )
    ap.add_argument(
        "--digivault-token",
        default=os.environ.get("DIGIVAULT_BEARER_TOKEN", "").strip(),
        help="Bearer token for digivault writes (optional if auth disabled)",
    )
    ap.add_argument(
        "--sinks",
        default=None,
        help="Comma-separated sinks overriding manifest (vault,search)",
    )
    ap.add_argument(
        "--digisearch-url",
        default=os.environ.get("DIGISEARCH_URL", "http://127.0.0.1:8002"),
    )
    ap.add_argument(
        "--digikey-url",
        default=os.environ.get("DIGIKEY_URL", "http://127.0.0.1:8005"),
    )
    ap.add_argument(
        "--api-key",
        default=os.environ.get("DIGISEARCH_SEED_API_KEY", ""),
    )
    ap.add_argument(
        "--source-prefix",
        default=os.environ.get("DIGISEARCH_ONBOARD_REMOTE_PREFIX", "").strip() or None,
    )
    ap.add_argument(
        "--repo-root",
        type=Path,
        default=None,
        help="Monorepo root for static/openapi/repo globs (default: detected)",
    )
    ap.add_argument(
        "--dry-run",
        action="store_true",
        help="Classify + ingest sources into workdir; skip vault/search sinks and live crawl IO is still used unless --skip-crawl",
    )
    ap.add_argument(
        "--skip-crawl",
        action="store_true",
        help="Skip website scrape/classify/fetch (static/openapi/repo only)",
    )
    args = ap.parse_args(argv)

    manifest = load_manifest(args.manifest)
    sinks: tuple[str, ...] | None = None
    if args.sinks:
        sinks = tuple(s.strip() for s in args.sinks.split(",") if s.strip())

    vault_root = args.vault_root
    if vault_root is None:
        env_root = (os.environ.get("DIGIVAULT_ROOT") or "").strip()
        vault_root = Path(env_root) if env_root else None

    # Dry-run without crawl: avoid network for manifest validation smoke
    skip_crawl = args.skip_crawl or (
        args.dry_run and not (os.environ.get("DOCS_ONBOARD_DRY_RUN_CRAWL") or "").strip()
    )

    ws = Workspace.create(args.workdir)
    result = run_onboard(
        manifest,
        ws,
        vault_root=vault_root,
        digivault_url=args.digivault_url,
        digivault_token=args.digivault_token,
        sinks=sinks,
        digisearch_url=args.digisearch_url,
        digikey_url=args.digikey_url,
        api_key=args.api_key,
        source_prefix=args.source_prefix,
        repo_root=args.repo_root,
        dry_run=args.dry_run,
        skip_crawl=skip_crawl,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 2 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
