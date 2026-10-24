#!/usr/bin/env python3
"""Verify relative Markdown links from an allowlisted set of files (repo root)."""

from __future__ import annotations

import re
import subprocess
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

FENCE_RE = re.compile(r"^```.*?^```", re.MULTILINE | re.DOTALL)


def _strip_fenced_code(text: str) -> str:
    """Remove fenced code blocks so sample markdown in plans is not link-checked."""
    return FENCE_RE.sub("", text)


def _is_excluded(rel_posix: str) -> bool:
    return any(rel_posix == p.rstrip("/") or rel_posix.startswith(p) for p in EXCLUDE_PREFIXES)


def _gitignore_paths(candidates: set[str]) -> frozenset[str]:
    """The subset of `candidates` that git considers ignored.

    Asking git rather than matching `.gitignore` text ourselves is the point:
    the format carries `!` negations, anchored paths and per-directory ignore
    files, and a hand-rolled subset silently disagrees with `git status` on
    exactly the cases nobody tests locally. `EXCLUDE_PREFIXES` stays as the
    fast path for the directories that are ignored in every checkout.

    Falls back to "nothing is ignored" when git is missing or the tree is not
    a checkout (a tarball export, a vendored copy). Reporting every link as
    broken there would be worse than scanning a little too much.
    """
    if not candidates:
        return frozenset()
    try:
        proc = subprocess.run(
            [
                "git",
                "-C",
                str(REPO_ROOT),
                # A developer's global excludes file has no business deciding
                # what a repo check covers: a `core.excludesFile` holding
                # `*.md` would drop every doc from the scan and leave
                # `make doc-check` passing vacuously.
                "-c",
                "core.excludesFile=/dev/null",
                "check-ignore",
                # NUL-delimited both ways: on output git C-quotes any path that
                # is not plain ASCII (`"uni/caf\303\251.md"`), and on input a
                # path containing a newline would split into two paths. Either
                # way the answer would not round-trip to the set passed in.
                "-z",
                "--stdin",
            ],
            input=b"\0".join(p.encode("utf-8", "surrogateescape") for p in sorted(candidates)),
            capture_output=True,
            check=False,
        )
    except (OSError, subprocess.SubprocessError):
        return frozenset()
    # Exit 1 means "no input path is ignored" — not an error.
    if proc.returncode not in (0, 1):
        # Say so rather than dropping the filter in silence. The realistic way
        # to land here is a candidate whose name reads as pathspec magic
        # (`:(glob)…`), which check-ignore refuses outright — it has no
        # `--literal-pathspecs`, so the query cannot be made literal. A green
        # doc-check running with a broken filter is worse than a loud one.
        sys.stderr.write(f"check_doc_links: git check-ignore exited {proc.returncode}; ")
        sys.stderr.write("treating every path as tracked.\n")
        sys.stderr.write(proc.stderr.decode("utf-8", "replace"))
        return frozenset()
    return frozenset(
        part.decode("utf-8", "surrogateescape") for part in proc.stdout.split(b"\0") if part
    )


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
    # Build output and vendored checkouts hold a copy of component docs
    # (AGENTS.md among them), and the relative links inside a copy do not
    # resolve from the copy's own location — so `npm run build` in
    # apps/digichat can make `make doc-check` fail on links that exist
    # nowhere in the tree.
    found = {p: p.relative_to(REPO_ROOT).as_posix() for p in set(out)}
    ignored = _gitignore_paths(set(found.values()))
    return sorted(p for p, rel in found.items() if rel not in ignored)


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
        text = _strip_fenced_code(md.read_text(encoding="utf-8", errors="replace"))
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
