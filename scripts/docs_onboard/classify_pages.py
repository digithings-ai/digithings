#!/usr/bin/env python3
"""Leaf: classify discovered pages as docs / pdf / asset / skip."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path
from urllib.parse import urlparse

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
    load_manifest,
)
from scripts.docs_onboard.workspace import Workspace

_DEFAULT_DOCS_HINTS = ("/docs", "/guide", "/api", "/reference", "/manual")


def _path_of(url: str) -> str:
    return urlparse(url).path or "/"


def _starts_with_any(path: str, prefixes: tuple[str, ...]) -> str | None:
    for prefix in prefixes:
        if not prefix:
            continue
        if path == prefix or path.startswith(prefix.rstrip("/") + "/") or path.startswith(prefix):
            return prefix
    return None


def classify_one(page: DiscoveredPage, manifest: OnboardManifest) -> ClassifiedPage:
    """Apply v1 heuristic rules to a single discovered page."""
    path = _path_of(page.final_url or page.url)
    ctype = (page.content_type or "").lower()
    reasons: list[str] = []

    skip_hit = _starts_with_any(path, manifest.skip_path_prefixes)
    if skip_hit is not None:
        return ClassifiedPage(
            page=page,
            page_class=PageClass.skip,
            score=0.0,
            reasons=(f"skip_prefix:{skip_hit}",),
        )

    is_pdf = path.lower().endswith(".pdf") or "pdf" in ctype
    if is_pdf:
        return ClassifiedPage(
            page=page,
            page_class=PageClass.pdf,
            score=100.0,
            reasons=("pdf_extension_or_type",),
        )

    docs_hit = _starts_with_any(path, manifest.docs_path_prefixes)
    if docs_hit is not None:
        return ClassifiedPage(
            page=page,
            page_class=PageClass.docs,
            score=80.0,
            reasons=(f"docs_prefix:{docs_hit}",),
        )

    for hint in _DEFAULT_DOCS_HINTS:
        if hint in path.lower():
            return ClassifiedPage(
                page=page,
                page_class=PageClass.docs,
                score=60.0,
                reasons=(f"path_hint:{hint}",),
            )

    host = urlparse(page.final_url or page.url).netloc.lower()
    if path in ("/", "") and host.startswith("docs."):
        return ClassifiedPage(
            page=page,
            page_class=PageClass.docs,
            score=20.0,
            reasons=("docs_host_root",),
        )

    if ctype.startswith("image/") or path.lower().endswith(
        (".png", ".jpg", ".jpeg", ".gif", ".svg")
    ):
        return ClassifiedPage(
            page=page,
            page_class=PageClass.asset,
            score=10.0,
            reasons=("image_asset",),
        )

    reasons.append("default_skip")
    return ClassifiedPage(page=page, page_class=PageClass.skip, score=0.0, reasons=tuple(reasons))


def classify_pages(manifest: OnboardManifest, workspace: Workspace) -> int:
    """Classify every page in ``pages.jsonl`` into ``classified.jsonl``."""
    workspace.clear_classified()
    n = 0
    for page in workspace.iter_pages():
        workspace.append_classified(classify_one(page, manifest))
        n += 1
    return n


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    args = ap.parse_args(argv)
    manifest = load_manifest(args.manifest)
    ws = Workspace.create(args.workdir)
    n = classify_pages(manifest, ws)
    print(f"classify_pages: wrote {n} rows → {ws.classified_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
