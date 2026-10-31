#!/usr/bin/env python3
"""Supabase freeze: no new Supabase usage while the exit is in flight (DIG-2887, step S0).

The repository is leaving Supabase (epic DIG-2887). Until the last caller has
moved, the set of files that talk to Supabase may only SHRINK. This gate scans
the tracked runtime files of the tree under test for Supabase usage markers and
compares the per-file hit counts with ``scripts/supabase_freeze_baseline.json``:

  * a file with markers that the baseline does not list is NEW usage,
  * a file whose marker count is above its baseline count GREW,
  * a new file under a Supabase migrations / functions directory is a new
    migration or edge function, whatever it contains.

With ``--base-ref`` the baseline itself is also compared with the baseline at
the tip of the base branch, and a baseline that grew (a new path or a higher
count) fails: the fix for new usage is to put it on Cloudflare (D1, KV, R2, a
Worker route), never to allowlist it. A base branch without the baseline file
is the introducing change and is not compared. A file that git sees as
renamed (``git diff -M``) keeps its old path's allowance, so moving code
between apps is not new usage as long as its count does not grow.

Shrinking is the point. When a change removes usage, regenerate the baseline
with ``--write-baseline`` so the allowance follows it down.

What counts as a marker (code and config only; ``*.md``, ``docs/``, tests and
this gate's own files are out of scope, since they describe usage rather than
perform it): ``SUPABASE_*`` / ``*_SUPABASE_*`` names, a ``*.supabase.co`` host,
``@supabase/`` packages, Python ``supabase`` imports, the ``supabase_io``
helper, and PostgREST ``/rest/v1/`` paths.

Only paths and counts are printed, never file content.

Exit codes: 0 clean, 1 new or grown usage, 2 tool error (fails closed).

Run locally:
    python3 scripts/check_supabase_freeze.py --base-ref origin/develop
    python3 scripts/check_supabase_freeze.py --write-baseline   # after a removal
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_REL = "scripts/supabase_freeze_baseline.json"
SELF_REL = "scripts/check_supabase_freeze.py"

MARKER = re.compile(
    r"\b[A-Z0-9_]*SUPABASE_[A-Z0-9_]+"
    r"|[a-z0-9-]+\.supabase\.co\b"
    r"|@supabase/"
    r"|^\s*(?:from|import)\s+supabase\b"
    r"|\bsupabase_io\b"
    r"|/rest/v1/",
    re.MULTILINE,
)

# Any new file here is a new migration or edge function.
STRUCTURAL_DIRS = ("digiquant/supabase/", "supabase/migrations/", "supabase/functions/")

SKIP_SUFFIXES = (
    ".md",
    ".mdx",
    ".txt",
    ".lock",
    ".png",
    ".jpg",
    ".jpeg",
    ".gif",
    ".svg",
    ".ico",
    ".webp",
    ".pdf",
    ".woff",
    ".woff2",
    ".ttf",
    ".zip",
    ".gz",
    ".parquet",
)
SKIP_PREFIXES = ("docs/", "openwiki/", "openspec/", "tests/", ".github/ISSUE_TEMPLATE/")
SKIP_FILES = {SELF_REL, BASELINE_REL, "package-lock.json", "uv.lock"}
TEST_PARTS = ("/test/", "/tests/", "/__tests__/", "/__mocks__/")
TEST_SUFFIXES = (".test.ts", ".test.tsx", ".test.js", ".test.mjs", ".spec.ts", ".spec.tsx")


class ToolError(RuntimeError):
    """The gate could not measure; it must fail closed rather than pass."""


def _git(root: Path, args: list[str]) -> str:
    proc = subprocess.run(["git", "-C", str(root)] + args, capture_output=True, text=True)
    if proc.returncode != 0:
        tail = (proc.stderr or "").strip().splitlines()
        raise ToolError(f"git {' '.join(args)} failed: {tail[-1] if tail else proc.returncode}")
    return proc.stdout


def in_scope(path: str) -> bool:
    """True for a tracked runtime file the freeze measures."""
    if path in SKIP_FILES or path.endswith(SKIP_SUFFIXES) or path.startswith(SKIP_PREFIXES):
        return False
    name = path.rsplit("/", 1)[-1]
    if name.startswith("test_") or name.endswith("_test.py") or name == "conftest.py":
        return False
    if path.endswith(TEST_SUFFIXES):
        return False
    return not any(part in f"/{path}" for part in TEST_PARTS)


def is_structural(path: str) -> bool:
    return any(path.startswith(d) or f"/{d}" in f"/{path}" for d in STRUCTURAL_DIRS)


def count_markers(text: str) -> int:
    return len(MARKER.findall(text))


def scan(root: Path) -> dict[str, int]:
    """path -> marker count (structural files always listed, count >= 1)."""
    counts: dict[str, int] = {}
    for path in _git(root, ["ls-files", "-z"]).split("\0"):
        if not path or not in_scope(path):
            continue
        try:
            text = (root / path).read_text(encoding="utf-8", errors="ignore")
        except (FileNotFoundError, IsADirectoryError):
            continue  # deleted in the work tree, or a submodule
        except OSError as exc:
            raise ToolError(f"{path} is not readable: {exc.strerror}")
        n = count_markers(text)
        if is_structural(path):
            n = max(n, 1)
        if n:
            counts[path] = n
    return counts


def load_entries(raw: str, source: str) -> dict[str, int]:
    try:
        data = json.loads(raw)
    except ValueError as exc:
        raise ToolError(f"{source} is not valid JSON: {exc}")
    entries = data.get("entries") if isinstance(data, dict) else None
    if not isinstance(entries, dict) or not all(isinstance(v, int) for v in entries.values()):
        raise ToolError(f"{source} needs an 'entries' object of path -> integer count")
    return dict(entries)


def compare(allowed: dict[str, int], found: dict[str, int]) -> list[str]:
    findings = []
    for path in sorted(found):
        n, cap = found[path], allowed.get(path)
        if cap is None:
            kind = "NEW-MIGRATION" if is_structural(path) else "NEW"
            findings.append(f"{kind} {path}: {n} Supabase marker(s), not in the freeze baseline")
        elif n > cap:
            findings.append(f"GREW {path}: {n} Supabase marker(s), baseline allows {cap}")
    return findings


def baseline_growth(root: Path, base_ref: str, head: dict[str, int]) -> list[str]:
    sha = _git(root, ["rev-parse", "--verify", f"{base_ref}^{{commit}}"]).strip()
    if not _git(root, ["ls-tree", sha, "--", BASELINE_REL]).strip():
        return []  # the change that introduces the baseline
    base = load_entries(_git(root, ["show", f"{sha}:{BASELINE_REL}"]), f"{base_ref}:{BASELINE_REL}")
    moves = renames(root, sha)
    out = []
    for path in sorted(head):
        if path not in base:
            src = moves.get(path)
            # A file moved by git (rename detection) keeps its allowance, as
            # long as the old path left the baseline and the count did not grow.
            if src in base and src not in head and head[path] <= base[src]:
                continue
            out.append(f"BASELINE-NEW {path}: added to the freeze baseline")
        elif head[path] > base[path]:
            out.append(f"BASELINE-GREW {path}: {base[path]} -> {head[path]}")
    return out


def renames(root: Path, base_sha: str) -> dict[str, str]:
    """``{new_path: old_path}`` for files git sees as renamed since the base."""
    raw = _git(root, ["diff", "--name-status", "-M50%", base_sha, "HEAD"])
    moved = {}
    for line in raw.splitlines():
        parts = line.split("\t")
        if len(parts) == 3 and parts[0].startswith("R"):
            moved[parts[2]] = parts[1]
    return moved


def render(entries: dict[str, int]) -> str:
    doc = {
        "_comment": (
            "Supabase freeze baseline (DIG-2887 S0). May only shrink. "
            "Regenerate with: python3 scripts/check_supabase_freeze.py --write-baseline"
        ),
        "entries": dict(sorted(entries.items())),
    }
    return json.dumps(doc, indent=2) + "\n"


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    ap.add_argument("--root", type=Path, default=REPO_ROOT)
    ap.add_argument("--base-ref", help="also refuse a baseline that grew against this ref")
    ap.add_argument(
        "--write-baseline", action="store_true", help="rewrite the baseline from the tree"
    )
    args = ap.parse_args(argv)
    root = args.root.resolve()
    try:
        found = scan(root)
        if args.write_baseline:
            target = root / BASELINE_REL
            target.parent.mkdir(parents=True, exist_ok=True)
            target.write_text(render(found), encoding="utf-8")
            print(
                f"supabase-freeze: wrote {BASELINE_REL} ({len(found)} file(s), {sum(found.values())} marker(s))"
            )
            return 0
        try:
            raw = (root / BASELINE_REL).read_text(encoding="utf-8")
        except OSError as exc:
            raise ToolError(f"{BASELINE_REL} is not readable: {exc.strerror}")
        allowed = load_entries(raw, BASELINE_REL)
        findings = compare(allowed, found)
        if args.base_ref:
            findings += baseline_growth(root, args.base_ref, allowed)
    except ToolError as exc:
        print(f"supabase-freeze: TOOL ERROR: {exc}", file=sys.stderr)
        return 2
    if findings:
        print("supabase-freeze: FAIL. New Supabase usage is frozen while the exit runs (DIG-2887).")
        for line in findings:
            print(f"  {line}")
        print(
            "  Put new data on Cloudflare (D1, KV, R2, a Worker route) instead. Do not grow the baseline."
        )
        return 1
    stale = sorted(p for p in allowed if allowed[p] > found.get(p, 0))
    print(
        f"supabase-freeze: OK ({len(found)} file(s) with Supabase markers, all within the baseline)"
    )
    if stale:
        print(f"  {len(stale)} baseline entr(y/ies) can shrink: run with --write-baseline")
    return 0


if __name__ == "__main__":
    sys.exit(main())
