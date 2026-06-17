#!/usr/bin/env python3
"""
audit_config_references.py — Report how often each tracked config file is referenced in the repo.

Uses `git grep` (tracked files only) for basename matches and `config/<name>` path matches.
Low counts are *heuristic*: dynamic paths, docs outside the repo, or renamed references can be missed.

Usage:
  python3 scripts/audit_config_references.py
  python3 scripts/audit_config_references.py --verbose
"""
from __future__ import annotations

import argparse
import subprocess
import sys
from pathlib import Path


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[1]


def _git_grep_files(repo: Path, pattern: str) -> list[str]:
    r = subprocess.run(
        ["git", "grep", "-l", "-F", pattern, "--", "."],
        cwd=repo,
        capture_output=True,
        text=True,
    )
    if r.returncode not in (0, 1):
        sys.stderr.write(r.stderr or "")
        return []
    return [ln.strip() for ln in r.stdout.splitlines() if ln.strip()]


def _classify(rel: str) -> str:
    """Rough bucket: runtime vs operator vs example vs policy."""
    name = Path(rel).name.lower()
    if name.endswith(".example") or "secrets" in name:
        return "example / secrets template"
    if name in ("mcp.claude-desktop.fragment.json", "mcp.secrets.env.example"):
        return "IDE / MCP wiring"
    if name in ("macro_series.yaml", "portfolio.json", "watchlist.md", "schedule.json"):
        return "pipeline / data feeds"
    if name == "investment-policy.md":
        return "policy"
    if "investment" in name or name == "preferences.md":
        return "portfolio & mandate"
    if name in ("data-sources.md", "email-research.md", "hedge-funds.md", "mcp-setup.md"):
        return "operator docs & research inputs"
    return "see RUNBOOK + skills"


def main() -> int:
    ap = argparse.ArgumentParser(description="Audit references to files under config/.")
    ap.add_argument(
        "--verbose",
        action="store_true",
        help="Print matching file lists for basename hits (can be long).",
    )
    args = ap.parse_args()
    repo = _repo_root()

    listed = subprocess.run(
        ["git", "ls-files", "-z", "config/"],
        cwd=repo,
        capture_output=True,
    )
    if listed.returncode != 0:
        print("git ls-files failed — run from a git checkout.", file=sys.stderr)
        return 1

    paths = [p.decode() for p in listed.stdout.split(b"\0") if p and not p.endswith(b"/")]

    rows: list[tuple[str, int, int, str]] = []
    for rel in sorted(paths):
        bn = Path(rel).name
        conf_path = f"config/{bn}"
        by_bn = _git_grep_files(repo, bn)
        by_path = _git_grep_files(repo, conf_path)
        # Exclude self-file hits from basename noise
        others_bn = [f for f in by_bn if f != rel]
        others_path = [f for f in by_path if f != rel]
        rows.append(
            (
                rel,
                len(others_bn),
                len(others_path),
                _classify(rel),
            )
        )

    print("# Config file reference audit\n")
    print("| File | Basename hits (excl. self) | `config/<file>` hits (excl. self) | Notes |")
    print("|------|---------------------------|-----------------------------------|-------|")
    for rel, c_bn, c_p, note in rows:
        flag = " ⚠️ low" if c_bn + c_p == 0 else ""
        print(f"| `{rel}` | {c_bn} | {c_p} | {note}{flag} |")

    print("\n**Interpretation:** “Runtime / pipeline” files should show multiple hits in `scripts/` and docs. ")
    print("“Low” means: verify the file is still part of your operator flow (RUNBOOK, skills) before deleting.")
    print("Secrets (`local.env`, `mcp.secrets.env`) are gitignored — not listed.\n")

    if args.verbose:
        print("---\n## Basename match lists\n")
        for rel, _, _, _ in rows:
            bn = Path(rel).name
            by_bn = [f for f in _git_grep_files(repo, bn) if f != rel]
            if by_bn:
                print(f"### {rel}\n")
                for f in sorted(by_bn):
                    print(f"- {f}")
                print()

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
