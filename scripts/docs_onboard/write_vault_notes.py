#!/usr/bin/env python3
"""Leaf: write classified docs/PDF content into a digivault vault."""

from __future__ import annotations

import argparse
import os
import sys
from datetime import datetime, timezone
from pathlib import Path

from digivault.vault import Vault

from scripts.docs_onboard.html_to_markdown import html_to_markdown
from scripts.docs_onboard.models import ClassifiedPage, OnboardManifest, PageClass, load_manifest
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace


def _pdf_text(path: Path) -> str:
    """Extract PDF text via digisearch parsers (no pdfplumber vendored here)."""
    try:
        from digisearch.ingestion.registry import ParserRegistry
    except ImportError as exc:  # pragma: no cover - exercised when digisearch missing
        raise RuntimeError(
            "PDF vault notes require digisearch. Install with: pip install -e ./digisearch"
        ) from exc
    doc = ParserRegistry().parse(path)
    return (doc.content or "").strip() + "\n"


def _note_body_for(classified: ClassifiedPage, workspace: Workspace) -> tuple[str, str]:
    """Return ``(title, body_markdown)`` for a classified page."""
    page = classified.page
    title = page.title or Path(page.url).name or "Untitled"
    if classified.page_class == PageClass.docs:
        if not page.html_path:
            return title, ""
        html_path = workspace.root / page.html_path
        if not html_path.is_file():
            return title, ""
        return title, html_to_markdown(html_path.read_text(encoding="utf-8", errors="replace"))
    if classified.page_class == PageClass.pdf:
        # Prefer downloaded asset from source_map
        for entry in workspace.iter_source_map():
            if entry.source_url in (page.url, page.final_url) and entry.local_path:
                asset = workspace.root / entry.local_path
                if asset.is_file():
                    return title, _pdf_text(asset)
        return title, ""
    return title, ""


def write_vault_notes(
    manifest: OnboardManifest,
    workspace: Workspace,
    vault: Vault,
) -> int:
    """Upsert digivault notes for classified docs + PDF pages. Returns count written."""
    written = 0
    ingested_at = datetime.now(timezone.utc).isoformat()
    for classified in workspace.iter_classified():
        if classified.page_class not in (PageClass.docs, PageClass.pdf):
            continue
        try:
            title, body = _note_body_for(classified, workspace)
        except Exception:
            # PDF parser / HTML read failures skip this page; do not abort the sink.
            continue
        if not body.strip():
            continue
        url = classified.page.final_url or classified.page.url
        slug = slug_for_url(url)
        tags = ["onboard", classified.page_class.value, f"client:{manifest.client}"]
        frontmatter = {
            "title": title,
            "tags": tags,
            "source_url": url,
            "content_type": classified.page.content_type or classified.page_class.value,
            "ingested_at": ingested_at,
            "client": manifest.client,
            "page_class": classified.page_class.value,
        }
        vault.write_note(
            slug,
            frontmatter=frontmatter,
            body=body,
            subdir=manifest.vault_subdir,
            overwrite=True,
        )
        written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    ap.add_argument(
        "--vault-root",
        type=Path,
        default=None,
        help="Vault root (default: DIGIVAULT_ROOT)",
    )
    args = ap.parse_args(argv)
    root = args.vault_root or Path((os.environ.get("DIGIVAULT_ROOT") or "").strip())
    if not root or not str(root):
        raise SystemExit("Pass --vault-root or set DIGIVAULT_ROOT")
    root.mkdir(parents=True, exist_ok=True)
    manifest = load_manifest(args.manifest)
    ws = Workspace.create(args.workdir)
    n = write_vault_notes(manifest, ws, Vault(root))
    print(f"write_vault_notes: wrote {n} notes → {root}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
