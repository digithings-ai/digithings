"""Leaf: ingest monorepo / GitHub documentation (Stage 3b)."""

from __future__ import annotations

import json
import os
import urllib.error
import urllib.request
from fnmatch import fnmatch
from pathlib import Path
from typing import Any  # score:allow untyped any — GitHub API JSON payloads

from scripts.docs_onboard.ingest_static import ingest_paths, resolve_globs
from scripts.docs_onboard.models import (
    OnboardManifest,
    PageClass,
    RepoSource,
    load_static_sources,
)
from scripts.docs_onboard.workspace import Workspace


def _globs_for(repo_source: RepoSource, repo_root: Path) -> tuple[str, ...]:
    if repo_source.globs:
        return repo_source.globs
    if repo_source.globs_file:
        cfg_path = Path(repo_source.globs_file)
        if not cfg_path.is_absolute():
            cfg_path = repo_root / cfg_path
        return load_static_sources(cfg_path).globs
    return ()


def _fetch_github_file(
    owner_repo: str,
    ref: str,
    path: str,
    *,
    token: str = "",
) -> bytes:
    """Download a single file via the GitHub Contents API (raw)."""
    url = f"https://raw.githubusercontent.com/{owner_repo}/{ref}/{path}"
    headers = {"User-Agent": "digithings-docs-onboard"}
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(url, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=60) as resp:
            return resp.read()
    except urllib.error.HTTPError as exc:
        detail = exc.read().decode()[:500]
        raise RuntimeError(f"GitHub fetch failed {exc.code} {url}: {detail}") from exc


def _list_github_tree(owner_repo: str, ref: str, *, token: str = "") -> list[str]:
    """List blob paths in a GitHub repo tree (recursive)."""
    api = f"https://api.github.com/repos/{owner_repo}/git/trees/{ref}?recursive=1"
    headers = {
        "User-Agent": "digithings-docs-onboard",
        "Accept": "application/vnd.github+json",
    }
    if token:
        headers["Authorization"] = f"Bearer {token}"
    req = urllib.request.Request(api, headers=headers, method="GET")
    with urllib.request.urlopen(req, timeout=60) as resp:
        payload: dict[str, Any] = json.loads(resp.read().decode())
    tree = payload.get("tree") or []
    out: list[str] = []
    for item in tree:
        if isinstance(item, dict) and item.get("type") == "blob" and item.get("path"):
            out.append(str(item["path"]))
    return out


def _match_globs(paths: list[str], globs: tuple[str, ...]) -> list[str]:
    """Simple pathlib-style match against repo-relative paths."""
    matched: list[str] = []
    for path in paths:
        for pattern in globs:
            if fnmatch(path, pattern) or fnmatch(path, pattern.lstrip("./")):
                matched.append(path)
                break
    return matched


def ingest_repo_docs(
    manifest: OnboardManifest,
    workspace: Workspace,
    *,
    repo_root: Path,
    github_token: str | None = None,
) -> int:
    """Ingest documentation from ``manifest.repo_source`` into the workspace."""
    src = manifest.repo_source
    if src is None:
        return 0

    if src.kind == "local":
        root = Path(src.path or ".")
        if not root.is_absolute():
            root = (repo_root / root).resolve()
        globs = _globs_for(src, repo_root)
        paths = resolve_globs(root, globs)
        return ingest_paths(
            manifest,
            workspace,
            paths=paths,
            repo_root=root,
            page_class=PageClass.repo_doc,
            reason="repo_source:local",
        )

    # github
    token = (
        github_token if github_token is not None else os.environ.get("GITHUB_TOKEN", "")
    ).strip()
    owner_repo = (src.github_repo or "").strip()
    globs = _globs_for(src, repo_root)
    tree = _list_github_tree(owner_repo, src.ref, token=token)
    matched = _match_globs(tree, globs)
    # Materialize into a temp staging dir under workspace, then ingest_paths
    stage = workspace.root / "repo_fetch"
    stage.mkdir(parents=True, exist_ok=True)
    staged: list[Path] = []
    for rel in matched:
        data = _fetch_github_file(owner_repo, src.ref, rel, token=token)
        dest = stage / rel
        dest.parent.mkdir(parents=True, exist_ok=True)
        dest.write_bytes(data)
        staged.append(dest)
    return ingest_paths(
        manifest,
        workspace,
        paths=staged,
        repo_root=stage,
        page_class=PageClass.repo_doc,
        reason=f"repo_source:github:{owner_repo}@{src.ref}",
    )
