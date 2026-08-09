"""Leaf: ingest OpenAPI/Swagger JSON files as ``PageClass.openapi`` pages."""

from __future__ import annotations

import json
from pathlib import Path

from scripts.docs_onboard.models import (
    ClassifiedPage,
    DiscoveredPage,
    OnboardManifest,
    PageClass,
    SourceMapEntry,
    load_openapi_sources,
)
from scripts.docs_onboard.naming import slug_for_url
from scripts.docs_onboard.workspace import Workspace


def openapi_to_markdown(path: Path, *, note_type: str) -> str:
    """Build a compact markdown body from an OpenAPI document for vault notes."""
    raw = path.read_text(encoding="utf-8", errors="replace")
    try:
        data = json.loads(raw)
    except json.JSONDecodeError:
        return f"# OpenAPI (unparsed)\n\nSource: `{path.name}`\n\n```\n{raw[:8000]}\n```\n"
    info = data.get("info") if isinstance(data, dict) else None
    title = "OpenAPI"
    version = ""
    description = ""
    if isinstance(info, dict):
        title = str(info.get("title") or title)
        version = str(info.get("version") or "")
        description = str(info.get("description") or "")
    paths = data.get("paths") if isinstance(data, dict) else None
    path_keys = sorted(paths.keys()) if isinstance(paths, dict) else []
    lines = [
        f"# {title}",
        "",
        f"> OpenAPI reference (`{note_type}`)" + (f" v{version}" if version else ""),
        "",
    ]
    if description:
        lines.extend([description.strip(), ""])
    lines.append(f"Source file: `{path.as_posix()}`")
    lines.append("Content-Type: application/openapi+json")
    lines.append("")
    lines.append(f"Paths ({len(path_keys)}):")
    for key in path_keys[:200]:
        lines.append(f"- `{key}`")
    if len(path_keys) > 200:
        lines.append(f"- … and {len(path_keys) - 200} more")
    lines.append("")
    return "\n".join(lines) + "\n"


def ingest_openapi_sources(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    repo_root: Path,
) -> int:
    """Stage OpenAPI files into the workdir as classified openapi pages."""
    if not manifest.openapi_sources:
        return 0
    cfg_path = Path(manifest.openapi_sources)
    if not cfg_path.is_absolute():
        cfg_path = repo_root / cfg_path
    if not cfg_path.is_file():
        raise FileNotFoundError(f"openapi_sources not found: {cfg_path}")
    cfg = load_openapi_sources(cfg_path)

    files_dir = workspace.root / "files"
    files_dir.mkdir(parents=True, exist_ok=True)
    count = 0
    for rel in cfg.files:
        src = Path(rel)
        if not src.is_absolute():
            src = repo_root / src
        if not src.is_file():
            continue
        try:
            rel_path = src.relative_to(repo_root.resolve())
        except ValueError:
            rel_path = Path(src.name)
        dest_name = slug_for_url(f"file:///{rel_path.as_posix()}") + ".md"
        dest = files_dir / dest_name
        dest.write_text(
            openapi_to_markdown(src, note_type=cfg.vault_note_type),
            encoding="utf-8",
        )
        local_rel = f"files/{dest_name}"
        source_url = f"repo://{manifest.client}/{rel_path.as_posix()}"
        workspace.append_classified(
            ClassifiedPage(
                page=DiscoveredPage(
                    url=source_url,
                    final_url=source_url,
                    content_type="application/openapi+json",
                    title=src.stem.replace("-", " ").replace("_", " "),
                    depth=0,
                    local_path=local_rel,
                    discovered_from="openapi_sources",
                ),
                page_class=PageClass.openapi,
                score=95.0,
                reasons=("openapi_sources", f"path:{rel_path.as_posix()}"),
            )
        )
        workspace.append_source_map(
            SourceMapEntry(
                local_path=local_rel,
                source_url=source_url,
                content_type="application/openapi+json",
            )
        )
        count += 1
    return count
