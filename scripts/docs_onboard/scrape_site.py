#!/usr/bin/env python3
"""Leaf: BFS crawl a docs site into a workdir (digifetch transport by default)."""

from __future__ import annotations

import argparse
import sys
from collections import deque
from collections.abc import Callable
from pathlib import Path
from urllib.parse import urlparse

from scripts.docs_onboard.html_links import extract_links, extract_title, looks_like_document
from scripts.docs_onboard.models import DiscoveredPage, OnboardManifest, load_manifest
from scripts.docs_onboard.naming import normalize_url, slug_for_url
from scripts.docs_onboard.workspace import Workspace

FetchHtml = Callable[[str], tuple[str, str, str]]  # final_url, content_type, text


def default_fetch_html(url: str) -> tuple[str, str, str]:
    """Production fetch via digifetch ``HttpFetcher``."""
    from digifetch.http import HttpFetcher

    with HttpFetcher() as fetcher:
        result = fetcher.fetch(url)
    ctype = (result.content_type or "text/html").split(";", 1)[0].strip().lower()
    return result.url, ctype, result.text


def _allowed_hosts(manifest: OnboardManifest) -> set[str]:
    if manifest.allowed_hosts:
        return {h.lower() for h in manifest.allowed_hosts}
    host = urlparse(manifest.seed_url).netloc.lower()
    return {host} if host else set()


def scrape_site(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    fetch_html: FetchHtml | None = None,
) -> int:
    """BFS from ``manifest.seed_url``; write pages + HTML under ``workspace``.

    Returns the number of discovered pages written. PDF/doc URLs are recorded
    but not downloaded (see ``fetch_docs``).
    """
    fetch = fetch_html or default_fetch_html
    hosts = _allowed_hosts(manifest)
    seed = normalize_url(manifest.seed_url)

    workspace.clear_pages()
    seen: set[str] = set()
    queue: deque[tuple[str, int, str | None, str]] = deque()
    # url, depth, discovered_from, link_text
    queue.append((seed, 0, None, ""))
    written = 0

    while queue and written < manifest.max_pages:
        url, depth, discovered_from, link_text = queue.popleft()
        key = normalize_url(url)
        if key in seen:
            continue
        if urlparse(key).netloc.lower() not in hosts:
            continue
        seen.add(key)

        if looks_like_document(key):
            ctype = (
                "application/pdf" if key.lower().endswith(".pdf") else "application/octet-stream"
            )
            workspace.append_page(
                DiscoveredPage(
                    url=key,
                    final_url=key,
                    content_type=ctype,
                    title=Path(urlparse(key).path).name,
                    depth=depth,
                    link_text=link_text,
                    discovered_from=discovered_from,
                )
            )
            written += 1
            continue

        if depth > manifest.max_depth:
            continue

        try:
            final_url, content_type, text = fetch(key)
        except Exception as exc:  # network / HTTP errors — record and continue
            workspace.append_page(
                DiscoveredPage(
                    url=key,
                    final_url=key,
                    content_type="error",
                    title=f"fetch_error: {exc}",
                    depth=depth,
                    link_text=link_text,
                    discovered_from=discovered_from,
                )
            )
            written += 1
            continue

        final_norm = normalize_url(final_url)
        ctype = (content_type or "text/html").split(";", 1)[0].strip().lower()
        title = extract_title(text) if "html" in ctype else ""
        html_rel: str | None = None
        if (
            "html" in ctype
            or text.lstrip().lower().startswith("<!DOCTYPE html")
            or "<html" in text[:200].lower()
        ):
            slug = slug_for_url(final_norm)
            dest = workspace.html_dir / f"{slug}.html"
            dest.write_text(text, encoding="utf-8")
            html_rel = f"html/{slug}.html"
            ctype = ctype if "html" in ctype else "text/html"

        workspace.append_page(
            DiscoveredPage(
                url=key,
                final_url=final_norm,
                content_type=ctype,
                title=title,
                depth=depth,
                link_text=link_text,
                discovered_from=discovered_from,
                html_path=html_rel,
            )
        )
        written += 1

        if "html" not in ctype or depth >= manifest.max_depth:
            continue

        for href, text_label in extract_links(text, final_norm):
            child = normalize_url(href)
            if urlparse(child).netloc.lower() not in hosts:
                continue
            if child in seen:
                continue
            queue.append((child, depth + 1, final_norm, text_label))

    return written


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
    args = ap.parse_args(argv)
    manifest = load_manifest(args.manifest)
    ws = Workspace.create(args.workdir)
    n = scrape_site(manifest, ws)
    print(f"scrape_site: wrote {n} pages → {ws.pages_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
