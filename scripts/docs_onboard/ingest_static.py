"""Leaf: ingest static file globs into the onboard workspace as repo_doc pages."""

from __future__ import annotations

import shutil
from pathlib import Path

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
    SourceMapEntry,
    load_static_sources,
)
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace


def _content_type_for(path: Path) -> str:
    suffix = path.suffix.lower()
    if suffix in (".md", ".markdown"):
        return "text/markdown"
    if suffix in (".html", ".htm"):
        return "text/html"
    if suffix == ".json":
        return "application/json"
    if suffix == ".txt":
        return "text/plain"
    return "application/octet-stream"


def resolve_globs(repo_root: Path, globs: tuple[str, ...]) -> list[Path]:
    """Expand globs under ``repo_root``; return sorted unique existing files."""
    found: set[Path] = set()
    for pattern in globs:
        pattern = pattern.strip()
        if not pattern:
            continue
        for match in sorted(repo_root.glob(pattern)):
            if match.is_file():
                found.add(match.resolve())
    return sorted(found)


def ingest_paths(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    paths: list[Path],
    repo_root: Path,
    page_class: PageClass,
    reason: str,
) -> int:
    """Copy files into the workdir and append classified pages. Returns count."""
    files_dir = workspace.root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    n = 0
    for src in paths:
        try:
            rel = src.relative_to(repo_root.resolve())
        except ValueError:
            rel = Path(src.name)
        dest_name = slug_for_url(f"file:///{rel.as_posix()}") + src.suffix
        dest = files_dir / dest_name
        shutil.copy2(src, dest)
        local_rel = f"files/{dest_name}"
        source_url = f"repo://{manifest.client}/{rel.as_posix()}"
        ctype = _content_type_for(src)
        page = DiscoveredPage(
            url=source_url,
            final_url=source_url,
            content_type=ctype,
            title=src.stem.replace("-", " ").replace("_", " "),
            depth=0,
            local_path=local_rel,
            discovered_from=reason,
        )
        workspace.append_classified(
            ClassifiedPage(
                page=page,
                page_class=page_class,
                score=90.0,
                reasons=(reason, f"path:{rel.as_posix()}"),
            )
        )
        workspace.append_source_map(
            SourceMapEntry(
                local_path=local_rel,
                source_url=source_url,
                content_type=ctype,
            )
        )
        n += 1
    return n


def ingest_static_sources(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    repo_root: Path,
    page_class: PageClass = PageClass.repo_doc,
    reason: str = "static_sources",
) -> int:
    """Copy static files into the workdir and append classified pages. Returns count."""
    if not manifest.static_sources:
        return 0
    cfg_path = Path(manifest.static_sources)
    if not cfg_path.is_absolute():
        cfg_path = repo_root / cfg_path
    if not cfg_path.is_file():
        raise FileNotFoundError(f"static_sources not found: {cfg_path}")
    cfg = load_static_sources(cfg_path)
    return ingest_paths(
        manifest,
        workspace,
        paths=resolve_globs(repo_root, cfg.globs),
        repo_root=repo_root,
        page_class=page_class,
        reason=reason,
    )
