#!/usr/bin/env python3
"""R0 client-literals guard (DIG-3689, lane S of the repo-split scrub).

The fresh public repo (R0) must not carry client names or tenant data. This
gate scans every tracked path that stays public (R0) for the client/tenant
literals named in DIG-3689 and fails on any hit that is not on the explicit
grandfather list. Findings carry path + line + pattern name, never the matched
value: CI logs on this repo are public. The census reads the git index
(`git ls-files`), so a new file that is not yet `git add`ed is invisible
to the gate — stage new files before trusting a local green.

Two deliberate design points, both documented so the next reader does not
re-derive them:

1. The patterns mirror the issue's reproduce grep
   (``datatap|online.compliance|occ_help|sitaas|zammad|help.online``,
   case-insensitive, ``.`` matching any char). ``help.online`` is read as
   ``help`` + any char + ``online``; the ticket text renders it with a doubled
   backslash, which as a regex would mean something else entirely.
2. Paths are classified by whole-file destination from the repo-split proposal
   (``docs/repo-split/``, PR #5695, section 3): anything whose whole file moves
   to R1-R7, or is slated for deletion, is skipped. Files that stay in R0 but
   carry a tenant block (e.g. the ``DIGI_TENANT_CORPUS_MAP`` fallback) are
   checked: a path move cannot remove a code block. An unmapped path is treated
   as R0 (public by default) until the P1.1 path manifest maps it; that mapping
   supersedes the prefix table below, it does not widen it.

The baseline file (``scripts/r0_client_literals_baseline.json``) is the
explicit grandfather list: every entry names the owning ticket. The gate fails
when a path has hits but no entry, when an entry's count moved in either
direction, or when an entry no longer hits at all (stale entries must be
deleted in the same diff that removes the literals).
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[1]
BASELINE_REL = Path("scripts/r0_client_literals_baseline.json")

#: (name, compiled case-insensitive pattern). ``.`` is any-char on purpose,
#: mirroring the issue's reproduce grep.
PATTERNS: tuple[tuple[str, "re.Pattern[str]"], ...] = (
    ("datatap", re.compile(r"datatap", re.IGNORECASE)),
    ("sitaas", re.compile(r"sitaas", re.IGNORECASE)),
    ("zammad", re.compile(r"zammad", re.IGNORECASE)),
    ("occ_help", re.compile(r"occ.help", re.IGNORECASE)),
    ("online-compliance", re.compile(r"online.compliance", re.IGNORECASE)),
    ("help-online", re.compile(r"help.online", re.IGNORECASE)),
)

#: Whole-file destinations to R1-R7 (private). A path under one of these
#: prefixes leaves R0 with its file, so the guard does not check it.
NON_R0_PREFIXES: tuple[str, ...] = (
    "digiquant/src/digiquant/strategies/",
    "digiquant/src/digiquant/sdca_mcp.py",
    "digiquant/src/digiquant/charts/sdca.py",
    "digiquant/supabase/",
    "digiquant/src/digiquant/research/config/",
    "apps/dashboard-api/",
    "apps/digiquant-runner/",
    "apps/dashboard/",
    "apps/digiquant-web/",
    "apps/digithings-web/",
    "packages/brand/",
    "apps/digithings-stack-cloudflare/",
    "apps/digichat-cloudflare/",
    "apps/digitrace-langfuse/",
    "apps/digithings-cron/",
    "infra/digichat-release/",
    "infra/digichat-digithings/",
    "apps/digidata-api/",
    "apps/digichat/config/datatap-trial-foundry.yaml",
    "apps/digichat/config/datatap-trial-test.yaml",
    "apps/digichat/config/examples/occ-embed.yaml",
    "apps/digichat/config/examples/datatap-mcp.yaml",
    "apps/digichat/config/examples/datatap-trial-deploy.md",
    "config/datatap_azure_access_register.json",
    "config/engagement-paths.json",
    "config/litellm.cheaperinference.yaml",
    "config/litellm.omniroute.yaml",
    "config/digiquant_models.yaml",
    "config/digiquant-model-prices.json",
    "config/dogfood-digiproject.yaml",
    "scripts/check_tenant_corpus_map.py",
    "tests/dq/strategies/",
    "tests/dg/test_tenant_corpus_parity.py",
    "tests/scripts/test_check_tenant_corpus_map.py",
    ".github/workflows/datatap-answer-check.yml",
    ".github/workflows/occ-invite-key-rollout.yml",
)

#: Delete-list from the proposal (section 3): internal agent wiring and doc
#: subtrees that never reach R0. Excluded, not checked.
DELETE_PREFIXES: tuple[str, ...] = (
    "docs/superpowers/",
    "docs/agent-backlog/",
    "docs/reviews/",
    "docs/plans/",
    "docs/projects/",
    "docs/dig-2041/",
    "docs/backlog/",
    "docs/scoring/",
    ".claude/",
    ".cursor/",
    "agents/",
    "projects/",
)

_SKIP_PREFIXES = NON_R0_PREFIXES + DELETE_PREFIXES


def is_r0(rel: str) -> bool:
    """True when a repo-relative path stays public (R0)."""
    return not rel.startswith(_SKIP_PREFIXES)


def iter_tracked_files(root: Path) -> list[str]:
    """Tracked paths from the index; falls back to a filesystem walk."""
    try:
        out = subprocess.run(
            ["git", "-C", str(root), "ls-files", "-z"],
            capture_output=True,
            text=True,
            check=True,
        )
    except Exception:
        return sorted(
            str(p.relative_to(root))
            for p in root.rglob("*")
            if p.is_file() and ".git/" not in str(p)
        )
    return [p for p in out.stdout.split("\0") if p]


def matching_lines(path: Path) -> list[tuple[int, str]]:
    """(lineno, pattern-name) for each matching line; binary files skipped."""
    try:
        raw = path.read_bytes()
    except OSError:
        return []
    if b"\x00" in raw[:8192]:
        return []
    hits: list[tuple[int, str]] = []
    for lineno, line in enumerate(raw.decode("utf-8", errors="replace").splitlines(), start=1):
        for name, rx in PATTERNS:
            if rx.search(line):
                hits.append((lineno, name))
                break
    return hits


def census(root: Path) -> dict[str, list[tuple[int, str]]]:
    """Per-path hits over R0 tracked files. Values stay in memory only."""
    found: dict[str, list[tuple[int, str]]] = {}
    for rel in iter_tracked_files(root):
        if not is_r0(rel):
            continue
        hits = matching_lines(root / rel)
        if hits:
            found[rel] = hits
    return found


def load_baseline(root: Path) -> dict[str, dict[str, object]]:
    with open(root / BASELINE_REL, encoding="utf-8") as fh:
        data = json.load(fh)
    entries = data.get("entries", {})
    assert isinstance(entries, dict), "baseline entries must be an object"
    return entries


def check(
    found: dict[str, list[tuple[int, str]]],
    baseline: dict[str, dict[str, object]],
) -> list[str]:
    """Human-readable failures; empty means green. No values printed."""
    failures: list[str] = []
    for rel in sorted(found):
        entry = baseline.get(rel)
        if entry is None:
            failures.append(
                f"NEW {rel}: {len(found[rel])} matching line(s), no baseline "
                "entry (grandfather it with the owning ticket or remove them)"
            )
        elif entry.get("count") != len(found[rel]):
            failures.append(
                f"COUNT {rel}: baseline says {entry.get('count')}, measured {len(found[rel])}"
            )
    for rel in sorted(baseline):
        if rel not in found:
            failures.append(f"STALE {rel}: baseline entry no longer hits, delete it")
        elif not is_r0(rel):
            failures.append(f"SCOPE {rel}: baseline entry is not an R0 path, delete it")
    return failures


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--root", default=str(REPO_ROOT))
    ap.add_argument(
        "--census",
        action="store_true",
        help="print per-path matching-line counts and exit 0",
    )
    args = ap.parse_args(argv)
    root = Path(args.root)
    found = census(root)
    if args.census:
        for rel in sorted(found):
            print(f"{len(found[rel]):5d} {rel}")
        print(f"{len(found)} R0 paths with hits")
        return 0
    baseline = load_baseline(root)
    failures = check(found, baseline)
    if failures:
        print(f"r0-client-literals: {len(failures)} finding(s)")
        for failure in failures:
            print(f"  FAIL  [{failure}]")
        return 1
    print(f"r0-client-literals: clean over {len(found)} baselined path(s)")
    return 0


if __name__ == "__main__":
    sys.exit(main())
