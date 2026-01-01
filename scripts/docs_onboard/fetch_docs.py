#!/usr/bin/env python3
"""Leaf: download classified PDF/doc assets into the workdir."""

from __future__ import annotations

import argparse
import hashlib
import sys
from collections.abc import Callable
from pathlib import Path

from scripts.docs_onboard.models import OnboardManifest, PageClass, SourceMapEntry, load_manifest
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace

DownloadFn = Callable[[str], bytes]


def default_download(url: str) -> bytes:
    """Production download via digifetch ``HttpFetcher.download``."""
    from digifetch.http import HttpFetcher

    with HttpFetcher() as fetcher:
        result = fetcher.download(url)
    return result.content


def _asset_name(url: str) -> str:
    slug = slug_for_url(url)
    suffix = Path(url.split("?", 1)[0]).suffix.lower() or ".bin"
    if len(suffix) > 8:
        suffix = ".bin"
    digest = hashlib.sha1(url.encode("utf-8")).hexdigest()[:8]
    return f"{slug}-{digest}{suffix}"


def fetch_docs(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    download: DownloadFn | None = None,
) -> int:
    """Download classified ``pdf`` (and ``asset``) pages into ``assets/``.

    Idempotent: skips when a source_map entry already exists for the same URL.
    ``manifest`` is accepted for CLI symmetry (filters reserved for later).
    """
    _ = manifest
    dl = download or default_download
    existing = {e.source_url for e in workspace.iter_source_map()}
    written = 0
    for classified in workspace.iter_classified():
        if classified.page_class not in (PageClass.pdf, PageClass.asset):
            continue
        url = classified.page.final_url or classified.page.url
        if url in existing:
            continue
        try:
            content = dl(url)
        except Exception as exc:
            workspace.append_source_map(
                SourceMapEntry(
                    local_path="",
                    source_url=url,
                    content_type=f"error:{exc}",
                )
            )
            continue
        name = _asset_name(url)
        dest = workspace.assets_dir / name
        dest.write_bytes(content)
        rel = f"assets/{name}"
        ctype = classified.page.content_type or "application/octet-stream"
        workspace.append_source_map(
            SourceMapEntry(local_path=rel, source_url=url, content_type=ctype)
        )
        existing.add(url)
        written += 1
    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    args = ap.parse_args(argv)
    manifest = load_manifest(args.manifest)
    ws = Workspace.create(args.workdir)
    n = fetch_docs(manifest, ws)
    print(f"fetch_docs: downloaded {n} assets → {ws.assets_dir}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
