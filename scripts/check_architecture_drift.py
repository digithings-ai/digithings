#!/usr/bin/env python3
"""Conservative ``ARCHITECTURE.md`` drift heuristic (#3525).

AGENTS.md requires updating ``{component}/ARCHITECTURE.md`` after interface or
behavior changes, but nothing checks it, so docs rot silently. This script
*proposes* candidates for a human to judge — it never edits docs and, by
default, never fails anything.

Heuristic
---------
A module (a directory holding an ``ARCHITECTURE.md``) is a *candidate* when its
**interface** moved at least ``--min-lag-days`` after its ``ARCHITECTURE.md``
did, and that interface move is inside the ``--window-days`` lookback. Interface
paths are a tight, tunable allowlist of the module's public surface — package
barrels (``__init__.py``), entry points (``server.py``/``app.py``/``cli.py``/…),
declared entry points (``pyproject.toml``), routes/pages and public schemas — not
"any file under ``src``", which would flag every refactor. A doc committed after
the interface change is treated as maintained, however recently.

The minimum lag exists so a doc follow-up in the same PR (committed hours later)
does not read as drift; only a doc that stayed behind by ``min-lag-days`` does.

Flag, do not fail: exit 0 always unless ``--exit-code`` is passed, in which case
the exit code is ``2`` when candidates exist (``0`` otherwise). The scheduled
job uses ``--exit-code`` only to decide whether to file the tracker issue.

Usage
-----
::

    python3 scripts/check_architecture_drift.py
    python3 scripts/check_architecture_drift.py --format json --exit-code
"""

from __future__ import annotations

import argparse
import glob
import json
import subprocess
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Any  # score:allow untyped any — JSON payloads are arbitrary

REPO_ROOT = Path(__file__).resolve().parent.parent
DEFAULT_WINDOW_DAYS = 30
DEFAULT_MIN_LAG_DAYS = 3
EXIT_CANDIDATES = 2

# Directories never walked for modules (vendored, generated, confidential).
# `openwiki/` holds generated mirror pages named ARCHITECTURE.md — not modules.
_SKIP_DIR_PARTS = frozenset(
    {".git", "node_modules", ".venv", ".next", "__pycache__", "htmlcov", "projects", "openwiki"}
)

# Interface patterns per module, relative to the module root. ``**`` is recursive
# (glob). Kept deliberately narrow: a hit means the *public surface* moved, not
# that some implementation file changed. Tune here before enabling.
DEFAULT_INTERFACE_PATTERNS: tuple[str, ...] = (
    "pyproject.toml",
    "src/**/__init__.py",
    "src/**/server.py",
    "src/**/app.py",
    "src/**/main.py",
    "src/**/cli.py",
    "src/**/__main__.py",
    "src/**/api.py",
    "src/**/routes.py",
    "src/**/client.py",
    "src/**/models.py",
    "src/**/schemas.py",
    "src/**/types.py",
    "src/**/config.py",
    "src/**/settings.py",
)

MODULE_INTERFACE_PATTERNS: dict[str, tuple[str, ...]] = {
    "apps/digichat": (
        "package.json",
        "src/**/index.ts",
        "src/app/**/page.tsx",
        "src/app/**/route.ts",
        "src/app/**/layout.tsx",
    ),
    "packages/digichat-ui": ("package.json", "src/index.ts", "src/**/index.ts"),
    # Pre-move this was `cloudflare/digiweb` and covered both the kit
    # (`web/src/**`) and the reference app (`reference/app/**/page.tsx`) in one
    # module root. The #4306 move split them: the kit is `packages/ui`, and the
    # reference app is `apps/reference` — which has no ARCHITECTURE.md, so the
    # page globs belong to nothing and only the kit's interface is tracked here.
    "packages/ui": (
        "package.json",
        "src/index.ts",
        "src/**/index.ts",
    ),
}


@dataclass(frozen=True)
class Finding:
    """A module whose interface moved while its ARCHITECTURE.md sat still."""

    module: str
    doc_path: str
    doc_last_commit: str | None
    doc_age_days: int | None
    interface_commits: list[dict[str, str]]


@dataclass(frozen=True)
class Report:
    window_days: int
    min_lag_days: int
    modules_checked: int
    modules_unmonitored: list[str]
    findings: list[Finding]


def _git(repo_root: Path, *args: str) -> str:
    proc = subprocess.run(
        ["git", *args],
        cwd=repo_root,
        capture_output=True,
        text=True,
        check=False,
    )
    if proc.returncode != 0:
        raise RuntimeError(proc.stderr.strip() or f"git {' '.join(args)} failed")
    return proc.stdout


def discover_modules(repo_root: Path, max_depth: int = 2) -> list[Path]:
    """Module roots: an ``ARCHITECTURE.md`` at depth 1–2, repo root excluded."""
    modules: set[Path] = set()
    for doc in repo_root.rglob("ARCHITECTURE.md"):
        rel = doc.relative_to(repo_root)
        if len(rel.parts) - 1 > max_depth or rel.parts == ("ARCHITECTURE.md",):
            continue
        if _SKIP_DIR_PARTS.intersection(rel.parts):
            continue
        modules.add(doc.parent)
    return sorted(modules)


def interface_patterns(module_root: Path, repo_root: Path) -> tuple[str, ...]:
    key = module_root.relative_to(repo_root).as_posix()
    return MODULE_INTERFACE_PATTERNS.get(key, DEFAULT_INTERFACE_PATTERNS)


def interface_files(module_root: Path, patterns: tuple[str, ...]) -> list[Path]:
    """Expand the module's interface globs to concrete existing files."""
    found: set[Path] = set()
    for pattern in patterns:
        for hit in glob.glob(str(module_root / pattern), recursive=True):
            path = Path(hit)
            if path.is_file():
                found.add(path)
    return sorted(found)


def _commits_touching(repo_root: Path, paths: list[Path], since_iso: str) -> list[dict[str, str]]:
    """Unique commits touching any of ``paths`` since ``since_iso``, newest first."""
    seen: dict[str, dict[str, str]] = {}
    for start in range(0, len(paths), 100):
        chunk = paths[start : start + 100]
        out = _git(
            repo_root,
            "log",
            f"--since={since_iso}",
            "--format=%H%x1f%ct%x1f%cI%x1f%s",
            "--",
            *[str(p) for p in chunk],
        )
        for line in out.splitlines():
            if not line.strip():
                continue
            sha, ts, iso, subject = line.split("\x1f", 3)
            seen.setdefault(
                sha,
                {"sha": sha[:8], "ts": ts, "date": iso[:10], "subject": subject},
            )
    return sorted(seen.values(), key=lambda c: int(c["ts"]), reverse=True)


def _last_commit_ts(repo_root: Path, path: Path) -> int | None:
    out = _git(repo_root, "log", "-1", "--format=%ct", "--", str(path)).strip()
    return int(out) if out else None


def is_candidate(interface_last_ts: int | None, doc_last_ts: int | None, min_lag_days: int) -> bool:
    """Drift iff the interface moved at least ``min_lag_days`` after the doc did.

    A doc committed *after* the interface change is maintained, however recently.
    Requiring a minimum lag keeps a same-PR follow-up from reading as drift.
    """
    if interface_last_ts is None:
        return False
    if doc_last_ts is None:
        return True
    return (interface_last_ts - doc_last_ts) >= min_lag_days * 86_400


def evaluate(
    repo_root: Path,
    window_days: int = DEFAULT_WINDOW_DAYS,
    min_lag_days: int = DEFAULT_MIN_LAG_DAYS,
    now: datetime | None = None,
) -> Report:
    now = now or datetime.now(timezone.utc)
    since_iso = (now - timedelta(days=window_days)).isoformat()

    findings: list[Finding] = []
    unmonitored: list[str] = []
    modules = discover_modules(repo_root)

    for module_root in modules:
        rel = module_root.relative_to(repo_root).as_posix()
        paths = interface_files(module_root, interface_patterns(module_root, repo_root))
        if not paths:
            unmonitored.append(rel)
            continue

        interface_commits = _commits_touching(repo_root, paths, since_iso)
        if not interface_commits:
            continue

        doc = module_root / "ARCHITECTURE.md"
        doc_ts = _last_commit_ts(repo_root, doc)
        if not is_candidate(int(interface_commits[0]["ts"]), doc_ts, min_lag_days):
            continue

        doc_last = (
            datetime.fromtimestamp(doc_ts, tz=timezone.utc).date().isoformat()
            if doc_ts is not None
            else None
        )
        doc_age = (
            int((now - datetime.fromtimestamp(doc_ts, tz=timezone.utc)).days) if doc_ts else None
        )
        findings.append(
            Finding(
                module=rel,
                doc_path=doc.relative_to(repo_root).as_posix(),
                doc_last_commit=doc_last,
                doc_age_days=doc_age,
                interface_commits=interface_commits,
            )
        )

    return Report(
        window_days=window_days,
        min_lag_days=min_lag_days,
        modules_checked=len(modules),
        modules_unmonitored=sorted(unmonitored),
        findings=findings,
    )


def render_text(report: Report) -> str:
    lines = [
        f"ARCHITECTURE.md drift candidates (interface moved >{report.min_lag_days}d "
        f"after the doc, in the last {report.window_days}d)",
        "",
    ]
    if not report.findings:
        lines.append("No candidates.")
    for finding in report.findings:
        age = f"{finding.doc_age_days}d ago" if finding.doc_age_days is not None else "unknown"
        lines.append(f"- {finding.module} ({finding.doc_path})")
        lines.append(f"    doc last updated: {finding.doc_last_commit or 'never'} ({age})")
        lines.append(f"    interface changed in {len(finding.interface_commits)} commit(s):")
        for commit in finding.interface_commits[:5]:
            lines.append(f"      {commit['sha']} {commit['date']} {commit['subject']}")
    checked = report.modules_checked
    lines.append("")
    lines.append(f"{checked} module(s) checked; {len(report.findings)} candidate(s).")
    if report.modules_unmonitored:
        lines.append(
            "No interface paths matched (not monitored): " + ", ".join(report.modules_unmonitored)
        )
    return "\n".join(lines)


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--repo-root", type=Path, default=REPO_ROOT)
    parser.add_argument("--window-days", type=int, default=DEFAULT_WINDOW_DAYS)
    parser.add_argument("--min-lag-days", type=int, default=DEFAULT_MIN_LAG_DAYS)
    parser.add_argument("--format", choices=("text", "json"), default="text")
    parser.add_argument(
        "--exit-code",
        action="store_true",
        help=f"exit {EXIT_CANDIDATES} when candidates exist (default: always 0)",
    )
    args = parser.parse_args(argv)

    report = evaluate(
        args.repo_root,
        window_days=args.window_days,
        min_lag_days=args.min_lag_days,
    )

    if args.format == "json":
        payload: dict[str, Any] = asdict(report)
        print(json.dumps(payload, indent=2))
    else:
        print(render_text(report))

    if args.exit_code and report.findings:
        return EXIT_CANDIDATES
    return 0


if __name__ == "__main__":
    sys.exit(main())
