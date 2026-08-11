#!/usr/bin/env python3
"""Leaf: write classified docs/PDF/openapi/repo_doc content into digivault."""

from __future__ import annotations

import argparse
import json
import os
import re
import sys
import urllib.error
import urllib.request
from collections.abc import Callable
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Protocol  # score:allow untyped any — frontmatter / HTTP JSON

from digisearch.core.models import Segment
from digisearch.ingestion.segmenters.heading import heading_segments
from digivault.vault import Vault

from scripts.docs_onboard.html_to_markdown import html_to_markdown
from scripts.docs_onboard.models import ClassifiedPage, OnboardManifest, PageClass, load_manifest
from scripts.docs_onboard.naming import normalize_digi_product_names, slug_for_url
from scripts.docs_onboard.workspace import Workspace

_VAULT_PAGE_CLASSES = frozenset(
    {PageClass.docs, PageClass.pdf, PageClass.openapi, PageClass.repo_doc}
)
_H1 = re.compile(r"^#\s+(.+)$", re.MULTILINE)


def _markdown_title_from_body(body: str, fallback: str) -> str:
    match = _H1.search(body.lstrip())
    if match:
        return normalize_digi_product_names(match.group(1).strip())
    return fallback


def _segment_slug(segment: Segment) -> str:
    """Filesystem-safe suffix identifying a segment within its parent document."""
    page = segment.metadata.get("page")
    if isinstance(page, int):
        return f"p{page:03d}"
    raw = segment.label.split(":", 1)[-1]
    slug = re.sub(r"[^a-z0-9]+", "-", raw.lower()).strip("-")
    return (slug or f"seg{segment.index:03d}")[:48]


def _hub_body(title: str, child_names: list[str]) -> str:
    """Body for the parent note linking every child segment note in order."""
    lines = [f"# {title}", "", f"This document has {len(child_names)} sections:", ""]
    lines.extend(f"- [[{name}]]" for name in child_names)
    lines.append("")
    return "\n".join(lines)


class NoteWriter(Protocol):
    def write_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
        overwrite: bool = False,
    ) -> Any: ...


def _pdf_document(path: Path) -> Any:
    """Parsed digisearch Document for a PDF (carries page segments)."""
    try:
        from digisearch.ingestion.registry import ParserRegistry
    except ImportError as exc:  # pragma: no cover - exercised when digisearch missing
        raise RuntimeError(
            "PDF vault notes require digisearch. Install with: pip install -e ./digisearch"
        ) from exc
    return ParserRegistry().parse(path)


def _pdf_text(path: Path) -> str:
    """Extract PDF text via digisearch parsers (no pdfplumber vendored here)."""
    doc = _pdf_document(path)
    return (doc.content or "").strip() + "\n"


def _note_body_for(
    classified: ClassifiedPage, workspace: Workspace
) -> tuple[str, str, list[Segment]]:
    """Return (title, markdown body, structural segments) for a classified page."""
    page = classified.page
    title = normalize_digi_product_names(page.title or Path(page.url).name or "Untitled")
    if classified.page_class == PageClass.docs:
        if not page.html_path:
            return title, "", []
        html_path = workspace.root / page.html_path
        if not html_path.is_file():
            return title, "", []
        body = html_to_markdown(html_path.read_text(encoding="utf-8", errors="replace"))
        return title, body, heading_segments(body)
    if classified.page_class == PageClass.pdf:
        for entry in workspace.iter_source_map():
            if entry.source_url in (page.url, page.final_url) and entry.local_path:
                asset = workspace.root / entry.local_path
                if asset.is_file():
                    parsed = _pdf_document(asset)
                    body = (parsed.content or "").strip() + "\n"
                    return title, body, list(parsed.segments)
        return title, "", []
    if classified.page_class in (PageClass.openapi, PageClass.repo_doc):
        if not page.local_path:
            return title, "", []
        local = workspace.root / page.local_path
        if not local.is_file():
            return title, "", []
        text = local.read_text(encoding="utf-8", errors="replace")
        if local.suffix.lower() in (".html", ".htm"):
            body = html_to_markdown(text)
            return title, body, heading_segments(body)
        if local.suffix.lower() in (".md", ".markdown"):
            title = _markdown_title_from_body(text, title)
        body = text if text.endswith("\n") else text + "\n"
        return title, body, heading_segments(body)
    return title, "", []


class DigivaultApiWriter:
    """HTTP client that upserts notes via digivault ``POST /v1/notes``."""

    def __init__(
        self,
        base_url: str,
        *,
        bearer_token: str = "",
        post_json: Callable[[str, dict[str, Any], dict[str, str]], dict[str, Any]] | None = None,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.bearer_token = bearer_token.strip()
        self._post_json = post_json or _post_json

    def write_note(
        self,
        name: str,
        *,
        frontmatter: dict[str, Any] | None = None,
        body: str = "",
        subdir: str = "",
        overwrite: bool = False,
    ) -> dict[str, Any]:
        fm = dict(frontmatter or {})
        payload: dict[str, Any] = {
            "name": name,
            "body": body,
            "subdir": subdir,
            "overwrite": overwrite,
            "frontmatter": fm,
        }
        if "title" in fm:
            payload["title"] = fm.get("title")
        if "tags" in fm:
            payload["tags"] = fm.get("tags")
        headers: dict[str, str] = {}
        if self.bearer_token:
            headers["Authorization"] = f"Bearer {self.bearer_token}"
        return self._post_json(f"{self.base_url}/v1/notes", payload, headers)


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


def write_vault_notes(
    manifest: OnboardManifest,
    workspace: Workspace,
    vault: NoteWriter,
) -> int:
    """Upsert digivault notes for classified keep pages. Returns count written."""
    written = 0
    ingested_at = datetime.now(timezone.utc).isoformat()
    for classified in workspace.iter_classified():
        if classified.page_class not in _VAULT_PAGE_CLASSES:
            continue
        try:
            title, body, segments = _note_body_for(classified, workspace)
        except Exception:
            continue
        if not body.strip():
            continue
        url = classified.page.final_url or classified.page.url
        slug = slug_for_url(url)
        tags = ["onboard", classified.page_class.value, f"client:{manifest.client}"]
        frontmatter: dict[str, Any] = {
            "title": title,
            "tags": tags,
            "source_url": url,
            "content_type": classified.page.content_type or classified.page_class.value,
            "ingested_at": ingested_at,
            "client": manifest.client,
            "page_class": classified.page_class.value,
            "type": (
                "api_reference" if classified.page_class == PageClass.openapi else "reference"
            ),
            "status": "published",
        }
        if len(segments) < 2:
            vault.write_note(
                slug,
                frontmatter=frontmatter,
                body=body,
                subdir=manifest.vault_subdir,
                overwrite=True,
            )
            written += 1
            continue
        child_names: list[str] = []
        for segment in segments:
            child_name = f"{slug}__{_segment_slug(segment)}"
            child_fm = {
                **frontmatter,
                "title": f"{title} — {segment.label}",
                "segment_label": segment.label,
                "segment_index": segment.index,
                "parent_doc": slug,
            }
            vault.write_note(
                child_name,
                frontmatter=child_fm,
                body=segment.text if segment.text.endswith("\n") else segment.text + "\n",
                subdir=manifest.vault_subdir,
                overwrite=True,
            )
            child_names.append(child_name)
            written += 1
        vault.write_note(
            slug,
            frontmatter={**frontmatter, "segment_count": len(segments)},
            body=_hub_body(title, child_names),
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
    ap.add_argument(
        "--digivault-url",
        default=os.environ.get("DIGIVAULT_URL", "").strip() or None,
        help="digivault HTTP base (POST /v1/notes); alternative to --vault-root",
    )
    ap.add_argument(
        "--bearer-token",
        default=os.environ.get("DIGIVAULT_BEARER_TOKEN", "").strip(),
        help="Optional Bearer token for digivault writes",
    )
    args = ap.parse_args(argv)
    manifest = load_manifest(args.manifest)
    ws = Workspace.create(args.workdir)

    writer: NoteWriter
    if args.digivault_url:
        writer = DigivaultApiWriter(args.digivault_url, bearer_token=args.bearer_token)
        target = args.digivault_url
    else:
        root = args.vault_root or Path((os.environ.get("DIGIVAULT_ROOT") or "").strip())
        if not root or not str(root):
            raise SystemExit("Pass --vault-root / DIGIVAULT_ROOT or --digivault-url")
        root.mkdir(parents=True, exist_ok=True)
        writer = Vault(root)
        target = str(root)

    n = write_vault_notes(manifest, ws, writer)
    print(f"write_vault_notes: wrote {n} notes → {target}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
