#!/usr/bin/env python3
"""Parent orchestrator: scrape → classify → fetch → optional vault/search sinks."""

from __future__ import annotations

import argparse
import json
import os
import sys
from collections.abc import Callable
from pathlib import Path
from typing import Any

from digivault.vault import Vault

from scripts.docs_onboard.classify_pages import classify_pages
from scripts.docs_onboard.fetch_docs import fetch_docs
from scripts.docs_onboard.models import OnboardManifest, OnboardResult, PageClass, load_manifest
from scripts.docs_onboard.scrape_site import scrape_site
from scripts.docs_onboard.workspace import Workspace
from scripts.docs_onboard.write_search_index import write_search_index
from scripts.docs_onboard.write_vault_notes import write_vault_notes


def run_onboard(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    vault_root: Path | None = None,
    sinks: tuple[str, ...] | None = None,
    fetch_html: Callable[[str], tuple[str, str, str]] | None = None,
    download: Callable[[str], bytes] | None = None,
    digisearch_url: str = "http://127.0.0.1:8002",
    digikey_url: str = "http://127.0.0.1:8005",
    api_key: str = "",
    source_prefix: str | None = None,
    post_ingest: Callable[[dict[str, Any]], dict[str, Any]] | None = None,
) -> OnboardResult:
    """Execute the full leaf chain. Skip pages never reach vault/search writers."""
    errors: list[str] = []
    active_sinks = sinks if sinks is not None else manifest.sinks

    pages_seen = scrape_site(manifest, workspace, fetch_html=fetch_html)
    classify_pages(manifest, workspace)
    classified = list(workspace.iter_classified())
    docs_kept = sum(1 for c in classified if c.page_class in (PageClass.docs, PageClass.pdf))
    skipped = sum(1 for c in classified if c.page_class == PageClass.skip)

    try:
        fetch_docs(manifest, workspace, download=download)
    except Exception as exc:
        errors.append(f"fetch_docs: {exc}")

    vault_notes = 0
    search_docs = 0

    if "vault" in active_sinks:
        if vault_root is None:
            errors.append("vault sink requested but --vault-root / DIGIVAULT_ROOT missing")
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
        errors=tuple(errors),
    )


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument(
        "--vault-root",
        type=Path,
        default=None,
        help="digivault root (default: DIGIVAULT_ROOT)",
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
    args = ap.parse_args(argv)

    manifest = load_manifest(args.manifest)
    sinks: tuple[str, ...] | None = None
    if args.sinks:
        sinks = tuple(s.strip() for s in args.sinks.split(",") if s.strip())

    vault_root = args.vault_root
    if vault_root is None:
        env_root = (os.environ.get("DIGIVAULT_ROOT") or "").strip()
        vault_root = Path(env_root) if env_root else None

    ws = Workspace.create(args.workdir)
    result = run_onboard(
        manifest,
        ws,
        vault_root=vault_root,
        sinks=sinks,
        digisearch_url=args.digisearch_url,
        digikey_url=args.digikey_url,
        api_key=args.api_key,
        source_prefix=args.source_prefix,
    )
    print(json.dumps(result.model_dump(mode="json"), indent=2))
    return 2 if result.errors else 0


if __name__ == "__main__":
    sys.exit(main())
