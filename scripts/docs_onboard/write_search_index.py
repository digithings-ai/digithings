#!/usr/bin/env python3
"""Leaf: POST workdir HTML/PDF/markdown files to digisearch ``/ingest``.

Crawled HTML is converted to markdown (same ``html_to_markdown`` path as
``write_vault_notes``) before ingest so digisearch's ``MarkdownParser`` can
apply ``heading_segments``. Posting raw ``.html`` would strip headings via
BeautifulSoup ``get_text()`` and leave chunks without ``segment_label``.
"""

from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from pathlib import Path
from typing import Any  # score:allow untyped any — ingest JSON payloads are open dicts

from scripts.docs_onboard.html_to_markdown import html_to_markdown
from scripts.docs_onboard.models import OnboardManifest, PageClass, load_manifest
from scripts.docs_onboard.workspace import Workspace

PostIngest = Callable[[dict[str, Any]], dict[str, Any]]

_SEARCH_PAGE_CLASSES = frozenset({PageClass.docs, PageClass.openapi, PageClass.repo_doc})
_HTML_SUFFIXES = frozenset({".html", ".htm", ".xhtml"})


def _post_json(url: str, payload: dict[str, Any], headers: dict[str, str]) -> dict[str, Any]:
    data = json.dumps(payload).encode()
    req = urllib.request.Request(
        url,
        data=data,
        headers={**headers, "Content-Type": "application/json"},
        method="POST",
    )
    try:
        with urllib.request.urlopen(req, timeout=120) as resp:
            body = resp.read().decode()
            return json.loads(body) if body else {}
    except urllib.error.HTTPError as e:
        detail = e.read().decode()[:2000]
        raise RuntimeError(f"HTTP {e.code} {url}: {detail}") from e


def _oauth_token(digikey_url: str, api_key: str) -> str:
    out = _post_json(
        f"{digikey_url.rstrip('/')}/v1/oauth/token",
        {"grant_type": "api_key", "api_key": api_key},
        headers={},
    )
    token = out.get("access_token")
    if not token:
        raise RuntimeError(f"No access_token in digikey response: {out}")
    return str(token)


def _doc_type_for(classified_path: Path, page_class: PageClass, content_type: str) -> str:
    suffix = classified_path.suffix.lower()
    if suffix in (".md", ".markdown") or page_class in (PageClass.openapi, PageClass.repo_doc):
        if suffix in (".md", ".markdown") or "markdown" in content_type:
            return "markdown"
        if suffix in _HTML_SUFFIXES:
            return "html"
        return "plaintext"
    if suffix in _HTML_SUFFIXES or page_class == PageClass.docs:
        return "html"
    if suffix == ".pdf":
        return "pdf"
    return "plaintext"


def _html_search_sidecar(workspace: Workspace, rel: str, local: Path) -> tuple[Path, str]:
    """Write converted markdown under ``search_md/`` and return ``(path, rel)``.

    ``rel`` mirrors the source path with a ``.md`` suffix so container
    ``source_prefix`` mounts stay consistent with the workdir layout.
    """
    out_rel = f"search_md/{Path(rel).with_suffix('.md').as_posix()}"
    out_path = workspace.root / out_rel
    out_path.parent.mkdir(parents=True, exist_ok=True)
    markdown = html_to_markdown(local.read_text(encoding="utf-8", errors="replace"))
    out_path.write_text(markdown, encoding="utf-8")
    return out_path, out_rel


def _resolve_ingest_file(
    workspace: Workspace, rel: str, local: Path, page_class: PageClass, content_type: str
) -> tuple[Path, str, str]:
    """Return ``(absolute_path, workdir_rel, doc_type)`` for ``POST /ingest``.

    HTML sources are converted to markdown sidecars first (#2191).
    """
    if local.suffix.lower() in _HTML_SUFFIXES:
        path, out_rel = _html_search_sidecar(workspace, rel, local)
        return path, out_rel, "markdown"
    return local, rel, _doc_type_for(local, page_class, content_type)


def write_search_index(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    digisearch_url: str = "http://127.0.0.1:8002",
    digikey_url: str = "http://127.0.0.1:8005",
    api_key: str = "",
    source_prefix: str | None = None,
    post_ingest: PostIngest | None = None,
) -> int:
    """Ingest workdir docs into digisearch. Returns docs posted."""
    if post_ingest is None:
        key = api_key.strip()
        if not key:
            raise ValueError("api_key required when post_ingest is not injected")
        token = _oauth_token(digikey_url, key)
        base = digisearch_url.rstrip("/")
        auth = {"Authorization": f"Bearer {token}"}

        def post_ingest(payload: dict[str, Any]) -> dict[str, Any]:
            return _post_json(f"{base}/ingest", payload, auth)

    posted = 0
    for classified in workspace.iter_classified():
        if classified.page_class not in _SEARCH_PAGE_CLASSES:
            continue
        # Prefer local_path (static/repo/openapi); fall back to html_path (crawl)
        rel = classified.page.local_path or classified.page.html_path
        if not rel:
            continue
        local = workspace.root / rel
        if not local.is_file():
            continue
        ingest_path, ingest_rel, doc_type = _resolve_ingest_file(
            workspace, rel, local, classified.page_class, classified.page.content_type
        )
        if source_prefix:
            source = f"{source_prefix.rstrip('/')}/{ingest_rel}"
        else:
            source = str(ingest_path.resolve())
        url = classified.page.final_url or classified.page.url
        payload = {
            "source": source,
            "index_name": manifest.digisearch_index,
            "doc_type": doc_type,
            "metadata": {
                "source_url": url,
                "client": manifest.client,
                "page_class": classified.page_class.value,
            },
        }
        post_ingest(payload)
        posted += 1

    # PDF assets via source_map
    for entry in workspace.iter_source_map():
        if not entry.local_path or entry.content_type.startswith("error:"):
            continue
        if "pdf" not in entry.content_type.lower() and not entry.local_path.lower().endswith(
            ".pdf"
        ):
            continue
        local = workspace.root / entry.local_path
        if not local.is_file():
            continue
        if source_prefix:
            source = f"{source_prefix.rstrip('/')}/{entry.local_path}"
        else:
            source = str(local.resolve())
        payload = {
            "source": source,
            "index_name": manifest.digisearch_index,
            "doc_type": "pdf",
            "metadata": {
                "source_url": entry.source_url,
                "client": manifest.client,
                "page_class": PageClass.pdf.value,
            },
        }
        post_ingest(payload)
        posted += 1

    return posted


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--manifest", type=Path, required=True)
    ap.add_argument("--workdir", type=Path, required=True)
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
        help="Container-visible prefix (Compose digisearch); mirrors DIGISEARCH_SEED_REMOTE_PREFIX",
    )
    args = ap.parse_args(argv)
    manifest = load_manifest(args.manifest)
    ws = Workspace.create(args.workdir)
    n = write_search_index(
        manifest,
        ws,
        digisearch_url=args.digisearch_url,
        digikey_url=args.digikey_url,
        api_key=args.api_key,
        source_prefix=args.source_prefix,
    )
    print(f"write_search_index: posted {n} docs → index={manifest.digisearch_index}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
