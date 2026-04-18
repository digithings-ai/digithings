#!/usr/bin/env python3
"""Verify relative Markdown links from an allowlisted set of files (repo root)."""

from __future__ import annotations

import re
import sys
from pathlib import Path
from urllib.parse import unquote

REPO_ROOT = Path(__file__).resolve().parent.parent

# Do not scan these path prefixes (relative to repo root, use forward slashes).
EXCLUDE_PREFIXES: tuple[str, ...] = (
    ".git/",
    ".claude/",
    "node_modules/",
    ".venv/",
    "__pycache__/",
    "digisearch/devdata/",
    "projects/",
    "htmlcov/",
    ".pytest_cache/",
    "website/digichat/node_modules/",
)

ROOT_DOC_NAMES: frozenset[str] = frozenset(
    {
        "README.md",
        "AGENTS.md",
        "CLAUDE.md",
        "ARCHITECTURE.md",
        "CONTRIBUTING.md",
        "RELEASES.md",
        "ROADMAP.md",
        "SECURITY.md",
    }
)

LINK_RE = re.compile(r"!?\[[^\]]*]\(([^)]+)\)")


def _is_excluded(rel_posix: str) -> bool:
    return any(rel_posix == p.rstrip("/") or rel_posix.startswith(p) for p in EXCLUDE_PREFIXES)


def _collect_markdown_files() -> list[Path]:
    out: list[Path] = []
    for p in REPO_ROOT.rglob("*.md"):
        try:
            rel = p.relative_to(REPO_ROOT)
        except ValueError:
            continue
        rel_posix = rel.as_posix()
        if _is_excluded(rel_posix):
            continue
        name = rel.name
        parts = rel.parts
        if rel_posix.startswith("docs/"):
            out.append(p)
            continue
        if len(parts) == 1 and name in ROOT_DOC_NAMES:
            out.append(p)
            continue
        if name == "AGENTS.md" or name == "CLAUDE.md":
            out.append(p)
            continue
        if name.startswith("DIGI") and name.endswith(".md"):
            out.append(p)
            continue
    return sorted(set(out))


def _inside_repo(path: Path) -> bool:
    try:
        path.resolve().relative_to(REPO_ROOT.resolve())
    except ValueError:
        return False
    return True


def _link_ok(source_file: Path, raw_target: str) -> bool:
    t = raw_target.strip()
    if not t or t.startswith("#"):
        return True
    lower = t.lower()
    if lower.startswith(("http://", "https://", "mailto:", "ftp://")):
        return True
    path_part = t.split("#", 1)[0].split("?", 1)[0].strip()
    if not path_part:
        return True
    path_part = unquote(path_part)
    base = source_file.parent
    rel_candidate = (base / path_part).resolve()
    root_candidate = (REPO_ROOT / path_part).resolve()
    for candidate in (rel_candidate, root_candidate):
        if _inside_repo(candidate) and candidate.exists():
            return True
    return False


def main() -> int:
    files = _collect_markdown_files()
    errors: list[str] = []
    for md in files:
        text = md.read_text(encoding="utf-8", errors="replace")
        rel_md = md.relative_to(REPO_ROOT).as_posix()
        for m in LINK_RE.finditer(text):
            raw = m.group(1)
            if not _link_ok(md, raw):
                errors.append(f"{rel_md}: broken link target {raw!r}")

    if errors:
        print("check_doc_links: failures", file=sys.stderr)
        for e in errors:
            print(e, file=sys.stderr)
        return 1
    print(f"check_doc_links: OK ({len(files)} markdown files scanned)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
