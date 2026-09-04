#!/usr/bin/env python3
"""readiness.py — repo-health panel for housekeeping shifts.

Prints eight metric rows (value + band) measuring how agentic-ready the repo
is right now. Advisory ONLY: always exits 0, never a gate, never a pre-flight,
never auto-merged. If you are looking for the 4-dimension PR rubric, that is
scripts/score.py — a different tool measuring diffs, not the repo.

Usage:
    python3 scripts/readiness.py            # console table
    python3 scripts/readiness.py --write    # refresh computed table in docs/agents/READINESS.md
    python3 scripts/readiness.py --format json

Data comes from `gh` (issues, labels, PRs, workflow runs) and local git.
No network beyond what gh/git already use. Keep it stdlib-only.
"""

from __future__ import annotations

import argparse
import json
import re
import subprocess
import sys
from datetime import UTC, datetime, timedelta
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parent.parent
REPO = "digithings-ai/digithings"
READINESS_DOC = REPO_ROOT / "docs" / "agents" / "READINESS.md"
BEGIN_MARKER = "<!-- readiness:begin -->"
END_MARKER = "<!-- readiness:end -->"

# Band thresholds. Tunable; bands invite judgment, never gating.
STALE_DAYS = 90
WATCH_MISSING_LABELS = 5  # >N open issues missing priority/component -> sick
WATCH_STALE = 15  # >N stale open issues -> sick
WATCH_FAILURES = 3  # >N scheduled failures in 7d -> sick
WATCH_STUCK_DAYS = 7  # agent-task older than N days with no PR -> stuck
WATCH_MODULE_BEHIND = 50  # module branch >N behind develop -> sick
HEALTHY_MODULE_BEHIND = 5  # module branch within N of develop -> healthy
WATCH_RELEASE_AGE = 30  # release-please PR older than N days -> sick
HEALTHY_RELEASE_AGE = 7  # release-please PR within N days -> healthy
HEALTHY_STUCK = 3  # up to N stuck agent-tasks -> watch, more -> sick
WATCH_DOC_CANDIDATES = 3  # >N ARCHITECTURE drift candidates -> sick
MAX_STUCK_CHECKS = 20  # cap per-issue PR searches in m_dispatch (N+1 bound)

# The bare-minimum label set (2026-09 simplification, #3533). Anything else
# showing up on the repo is drift.
FLAT_KEEP = {
    "agent-task",
    "automerge-agent",
    "automerge-docs",
    "autorelease: pending",
    "autorelease: tagged",
    "bug",
    "ci:failure",
    "client-pilot",
    "epic",
    "provider-review",
    "reviewed:agent",
    "reviewed:owner",
    "security:finding",
}
# Open families: any label with these prefixes is expected (e.g. future
# reviewed:/autorelease: states). component:/priority: are closed — only the
# routing-listed components and four priorities count.
OPEN_FAMILIES = ("reviewed:", "autorelease:")

# Module dir -> source paths whose changes should be reflected in its ARCHITECTURE.md.
DOC_MODULES = {
    "digigraph": ["digigraph/src"],
    "digiquant": ["digiquant/src"],
    "digisearch": ["digisearch/src"],
    "digichat": ["frontend/digichat/src"],
    "digikey": ["digikey/src"],
    "digismith": ["digismith/src"],
    "digiclaw": ["digiclaw/src"],
    "digibase": ["digibase/src"],
    "digivault": ["digivault/src"],
}


def _run(args: list[str], **kwargs) -> str:  # type: ignore[no-untyped-def]
    return subprocess.check_output(args, text=True, cwd=REPO_ROOT, **kwargs).strip()


def _gh(*args: str) -> object:
    return json.loads(_run(["gh", *args]))


def band_of(ok: bool, warn: bool) -> str:
    if ok:
        return "healthy"
    return "watch" if warn else "sick"


# ── collectors: each returns (value, band, detail) ────────────────────────────


def m_backlog(issues: list[dict]) -> tuple[str, str, str]:
    """Open-issue hygiene: coverage, staleness, epics."""
    now = datetime.now(UTC)
    missing = [
        i["number"]
        for i in issues
        if not any(str(lbl.get("name", "")).startswith("priority:") for lbl in i["labels"])
        or not any(str(lbl.get("name", "")).startswith("component:") for lbl in i["labels"])
    ]
    stale = [
        i["number"]
        for i in issues
        if datetime.fromisoformat(i["updatedAt"].replace("Z", "+00:00"))
        < now - timedelta(days=STALE_DAYS)
    ]
    epics = sum(1 for i in issues if any(lbl.get("name") == "epic" for lbl in i["labels"]))
    value = f"{len(issues)} open ({len(missing)} missing labels, {len(stale)} stale, {epics} epics)"
    band = band_of(
        not missing and not stale,
        len(missing) <= WATCH_MISSING_LABELS and len(stale) <= WATCH_STALE,
    )
    detail = f"missing={missing[:10]} stale={stale[:10]}"
    return value, band, detail


def _expected_labels() -> set[str]:
    try:
        routing = json.loads((REPO_ROOT / "scripts" / "project_routing.json").read_text())
    except (OSError, json.JSONDecodeError):
        routing = {}
    expected = set(FLAT_KEEP)
    expected.update(k for k in routing if ":" in k and k.split(":")[0] in ("component",))
    expected.update(f"priority:{p}" for p in ("critical", "high", "medium", "low"))
    return expected


def _is_expected(name: str, expected: set[str]) -> bool:
    return name in expected or name.startswith(OPEN_FAMILIES)


def m_labels(names: list[str]) -> tuple[str, str, str]:
    """Label-set integrity vs the bare-minimum keep-list."""
    expected = _expected_labels()
    drift = sorted(n for n in set(names) if not _is_expected(n, expected))
    value = f"{len(names)} labels ({len(drift)} unexpected)"
    band = "healthy" if not drift else "sick"
    return value, band, f"unexpected={drift}" if drift else "matches keep-list"


def _git_mtime(path: str) -> int:
    try:
        out = _run(["git", "log", "-1", "--format=%ct", "--", path])
        return int(out) if out else 0
    except (subprocess.CalledProcessError, ValueError):
        return 0


def m_docs() -> tuple[str, str, str]:
    """ARCHITECTURE.md drift candidates + ADR numbering."""
    candidates = []
    for module, paths in DOC_MODULES.items():
        doc = f"{module}/ARCHITECTURE.md"
        if not (REPO_ROOT / doc).exists():
            continue
        doc_ts = _git_mtime(doc)
        src_ts = max([_git_mtime(p) for p in paths] + [0])
        if src_ts > doc_ts:
            candidates.append(module)
    adr_files = sorted((REPO_ROOT / "docs" / "adr").glob("[0-9]*-*.md"))
    nums = [int(f.name.split("-")[0]) for f in adr_files if f.name.split("-")[0].isdigit()]
    dupes = sorted({n for n in nums if nums.count(n) > 1})
    gaps = sorted(set(range(min(nums or [1]), max(nums or [1]))) - set(nums)) if nums else []
    problems = len(candidates) + len(dupes) + (1 if gaps else 0)
    value = f"{len(candidates)} drift candidates, {len(dupes)} dupes, {len(gaps)} gaps ({len(adr_files)} ADRs)"
    band = band_of(problems == 0, len(candidates) <= WATCH_DOC_CANDIDATES and not dupes)
    return value, band, f"candidates={candidates} dupes={dupes} gaps={gaps[:10]}"


def m_ops(failures: list[dict], ci_open: int) -> tuple[str, str, str]:
    """Scheduled-workflow failures (7d) + open ci:failure issues."""
    by_wf: dict[str, int] = {}
    latest: dict[str, str] = {}
    for f in failures:
        name = f.get("name", "?")
        by_wf[name] = by_wf.get(name, 0) + 1
        latest[name] = f.get("url", "")
    value = f"{len(failures)} failed runs / {len(by_wf)} workflows, {ci_open} open ci:failure"
    band = band_of(not failures, len(failures) <= WATCH_FAILURES)
    ranked = sorted(by_wf.items(), key=lambda kv: kv[1], reverse=True)[:5]
    detail = "; ".join(f"{name} x{count} {latest.get(name, '')}" for name, count in ranked)
    return value, band, detail or "no failures"


def _issue_tier(names: list[str], tiers: dict) -> str:
    comp = next((n for n in names if n.startswith("component:")), None)
    return tiers.get(comp, tiers.get("default", "cursor"))


def m_dispatch(issues: list[dict], tiers: dict) -> tuple[str, str, str]:
    """Open agent-task by tier + stuck (old, no linked PR)."""
    tasks = [i for i in issues if any(lbl.get("name") == "agent-task" for lbl in i["labels"])]
    by_tier: dict[str, int] = {}
    stuck = []
    cutoff = datetime.now(UTC) - timedelta(days=WATCH_STUCK_DAYS)
    for i in tasks:
        names = [str(lbl.get("name", "")) for lbl in i["labels"]]
        tier = _issue_tier(names, tiers)
        by_tier[tier] = by_tier.get(tier, 0) + 1
    candidates = [
        i for i in tasks if datetime.fromisoformat(i["updatedAt"].replace("Z", "+00:00")) < cutoff
    ]
    truncated = len(candidates) > MAX_STUCK_CHECKS
    for i in candidates[:MAX_STUCK_CHECKS]:
        try:
            prs = _gh(
                "pr",
                "list",
                "--repo",
                REPO,
                "--state",
                "open",
                "--search",
                f"#{i['number']} in:body",
                "--json",
                "number",
            )
            assert isinstance(prs, list)
            if not prs:
                stuck.append(i["number"])
        except (subprocess.CalledProcessError, AssertionError):
            continue
    value = f"{len(tasks)} agent-task {by_tier}, {len(stuck)} stuck"
    band = band_of(not stuck, len(stuck) <= HEALTHY_STUCK)
    detail = f"stuck={[f'#{n}' for n in stuck[:10]]}" + (" truncated=True" if truncated else "")
    return value, band, detail


def m_branches(behind: dict[str, int]) -> tuple[str, str, str]:
    """module/* behind-develop counts (the #2547 hazard)."""
    worst = max(behind.values()) if behind else 0
    value = f"{len(behind)} module branches, worst behind={worst}"
    band = band_of(worst <= 5, worst <= WATCH_MODULE_BEHIND)
    detail = ", ".join(f"{b}={n}" for b, n in sorted(behind.items(), key=lambda kv: -kv[1])[:8])
    return value, band, detail or "no module branches"


def m_releases(prs: list[dict]) -> tuple[str, str, str]:
    """Open release-please PRs + age (accumulation is intended; age is the signal)."""
    now = datetime.now(UTC)
    ages = []
    for pr in prs:
        created = datetime.fromisoformat(pr["createdAt"].replace("Z", "+00:00"))
        ages.append((pr["number"], (now - created).days))
    oldest = max((a for _, a in ages), default=0)
    value = f"{len(ages)} open release PRs, oldest {oldest}d"
    # Accumulation is the intended design; only age is a signal.
    band = band_of(oldest <= HEALTHY_RELEASE_AGE, oldest <= WATCH_RELEASE_AGE)
    base = f"https://github.com/{REPO}/pull"
    return value, band, ", ".join(f"#{n} ({a}d) {base}/{n}" for n, a in ages[:8]) or "none"


def m_bootstrap() -> tuple[str, str, str]:
    """Static presence checks for agent bootstrap essentials."""
    checks = {
        ".env.example": (REPO_ROOT / ".env.example").exists(),
        "Makefile task target": "make task" in (REPO_ROOT / "Makefile").read_text(),
        "agents.yml": (REPO_ROOT / "agents.yml").exists(),
        "project_routing.json": (REPO_ROOT / "scripts" / "project_routing.json").exists(),
    }
    missing = sorted(k for k, v in checks.items() if not v)
    value = f"{len(checks) - len(missing)}/{len(checks)} essentials present"
    band = "healthy" if not missing else "sick"
    return value, band, f"missing={missing}" if missing else "ok"


# ── live data fetching ────────────────────────────────────────────────────────


def fetch_issues() -> list[dict]:
    out = _gh(
        "issue",
        "list",
        "--repo",
        REPO,
        "--state",
        "open",
        "--limit",
        "500",
        "--json",
        "number,title,labels,updatedAt",
    )
    assert isinstance(out, list)
    return out


def collect() -> list[tuple[str, str, str, str]]:
    """Return [(dimension, value, band, detail)] for all eight rows.

    Advisory contract: never raise. Any unexpected failure degrades that row
    to unknown instead of killing the run.
    """
    rows: list[tuple[str, str, str, str]] = []

    def safe(dim: str, fn, *args) -> None:  # type: ignore[no-untyped-def]
        try:
            rows.append((dim, *fn(*args)))
        except Exception as exc:  # advisory tool: degrade, don't die
            rows.append((dim, "error", "unknown", f"{type(exc).__name__}: {str(exc)[:100]}"))

    try:
        issues = fetch_issues()
    except Exception as exc:
        return [("all", "gh failed", "unknown", f"{type(exc).__name__}: {str(exc)[:100]}")]
    safe("Backlog hygiene", m_backlog, issues)
    try:
        label_names = [
            str(lbl.get("name", ""))
            for lbl in _gh("label", "list", "--repo", REPO, "--limit", "200", "--json", "name")
        ]
    except Exception:
        label_names = []
    safe("Label-set integrity", m_labels, label_names)
    safe("Docs freshness", m_docs)
    try:
        since = (datetime.now(UTC) - timedelta(days=7)).strftime("%Y-%m-%d")
        # Note: -f form fields 404 on this endpoint; the query string works.
        failures = _gh(
            "api",
            f"/repos/{REPO}/actions/runs?status=failure&event=schedule"
            f"&created=%3E%3D{since}&per_page=100",
            "--paginate",
            "--jq",
            "[.workflow_runs[] | {name, url: .html_url}]",
        )
        assert isinstance(failures, list)
    except Exception:
        failures = []
    try:
        ci_open = sum(
            1 for i in issues if any(lbl.get("name") == "ci:failure" for lbl in i["labels"])
        )
    except Exception:
        ci_open = 0
    safe("Ops health", m_ops, failures, ci_open)
    try:
        routing = json.loads((REPO_ROOT / "scripts" / "project_routing.json").read_text())
        tiers = routing.get("tiers", {})
    except (OSError, json.JSONDecodeError):
        tiers = {}
    safe("Dispatch health", m_dispatch, issues, tiers)
    behind: dict[str, int] = {}
    try:
        # Only branches that are live routing targets (branches map in
        # project_routing.json). Dead module branches (atlas/olympus relics)
        # can't be deleted (module-branch-protection) — don't track them.
        try:
            routing_branches = json.loads(
                (REPO_ROOT / "scripts" / "project_routing.json").read_text()
            ).get("branches", {})
        except (OSError, json.JSONDecodeError):
            routing_branches = {}
        live = {v for v in routing_branches.values() if v.startswith("module/")}
        refs = _run(["git", "ls-remote", "origin"]).splitlines()
        for line in refs:
            m = re.search(r"refs/heads/(module/\S+)", line)
            if m and m.group(1) in live:
                branch = m.group(1)
                try:
                    n = int(
                        _run(["git", "rev-list", "--count", f"origin/{branch}..origin/develop"])
                    )
                except (subprocess.CalledProcessError, ValueError):
                    continue
                behind[branch] = n
    except Exception:
        pass
    safe("Branch routing health", m_branches, behind)
    try:
        rel = _gh(
            "pr",
            "list",
            "--repo",
            REPO,
            "--state",
            "open",
            "--search",
            "release-please",
            "--json",
            "number,createdAt",
        )
        assert isinstance(rel, list)
    except Exception:
        rel = []
    safe("Release discipline", m_releases, rel)
    safe("Bootstrap essentials", m_bootstrap)
    return rows


def render(rows: list[tuple[str, str, str, str]]) -> str:
    lines = [
        "| # | Dimension | Value | Band |",
        "|---|-----------|-------|------|",
    ]
    for idx, (dim, value, band, _detail) in enumerate(rows, 1):
        lines.append(f"| {idx} | {dim} | {value} | {band} |")
    return "\n".join(lines)


BAND_COLORS = {
    "healthy": ("#137333", "#e6f4ea"),
    "watch": ("#795809", "#fef7e0"),
    "sick": ("#a50e0e", "#fce8e6"),
    "unknown": ("#5f6368", "#f1f3f4"),
}

# Static "where to start" guidance per dimension for agents and humans.
ACTION_HINTS = {
    "Backlog hygiene": "Triage missing labels; close or re-scope stale issues.",
    "Label-set integrity": "Strip unexpected labels from issues, then delete the labels.",
    "Docs freshness": "A human judges each candidate; update the ARCHITECTURE.md or record why not.",
    "Ops health": "Open the latest failed run below; fix the cause or file an agent-task.",
    "Dispatch health": "Bounce agent-task on stuck issues (dispatch replay, dry-run first).",
    "Branch routing health": "Sync stale module branches via PR into module/* (force-push is blocked).",
    "Release discipline": "Decide per PR: merge for a real release, or leave it accumulating.",
    "Bootstrap essentials": "Restore the missing file/target by hand.",
}

SEVERITY_ORDER = {"sick": 0, "unknown": 1, "watch": 2, "healthy": 3}


def _esc(text: str) -> str:
    return text.replace("&", "&amp;").replace("<", "&lt;").replace(">", "&gt;")


def _linkify(text: str) -> str:
    """Link run URLs and #issue numbers in already-escaped text."""
    text = re.sub(
        r"https://github\.com/digithings-ai/digithings/[^\s),\"']+",
        lambda m: f"<a href='{m.group(0)}'>{m.group(0)}</a>",
        text,
    )
    return re.sub(
        r"#(\d{2,5})",
        lambda m: (
            f"<a href='https://github.com/digithings-ai/digithings/issues/{m.group(1)}'>#{m.group(1)}</a>"
        ),
        text,
    )


def render_html(rows: list[tuple[str, str, str, str]], stamp: str) -> str:
    """Self-contained dashboard page: inline CSS only, works from file://."""
    counts = {"healthy": 0, "watch": 0, "sick": 0, "unknown": 0}
    for _, _, band, _ in rows:
        counts[band] = counts.get(band, 0) + 1
    summary = " · ".join(
        f"<span class='pill {b}'>{counts[b]} {b}</span>"
        for b in ("healthy", "watch", "sick", "unknown")
    )
    cards = []
    ordered = sorted(enumerate(rows, 1), key=lambda t: (SEVERITY_ORDER.get(t[1][2], 9), t[0]))
    first_bad = next((t for t in ordered if t[1][2] in ("sick", "unknown")), None)
    if first_bad is None:
        start_here = "<p class='start ok'>All healthy — nothing needs you.</p>"
    else:
        num, (dim, value, band, _d) = first_bad
        start_here = (
            f"<p class='start'>Start here: <strong>#{num} {_esc(dim)}</strong> ({band}) — "
            f"{_esc(value)}. {_esc(ACTION_HINTS.get(dim, ''))}</p>"
        )
    for idx, (dim, value, band, detail) in ordered:
        fg, bg = BAND_COLORS.get(band, BAND_COLORS["unknown"])
        cards.append(
            f"<section class='card' style='border-left-color:{fg}'>"
            f"<header><span class='num'>#{idx}</span><h2>{_esc(dim)}</h2>"
            f"<span class='badge' style='color:{fg};background:{bg}'>{band}</span></header>"
            f"<p class='value'>{_esc(value)}</p>"
            f"<p class='hint'>{_esc(ACTION_HINTS.get(dim, ''))}</p>"
            f"<details><summary>detail</summary><code>{_linkify(_esc(detail))}</code></details>"
            "</section>"
        )
    return f"""<!DOCTYPE html>
<html lang="en">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width, initial-scale=1">
<title>digithings readiness — {stamp}</title>
<style>
:root {{ color-scheme: light dark; }}
body {{ font-family: -apple-system, system-ui, sans-serif; max-width: 880px; margin: 2rem auto; padding: 0 1rem; }}
header.top h1 {{ margin: 0 0 .25rem; font-size: 1.4rem; }}
header.top p {{ color: #5f6368; margin: 0 0 1rem; }}
.pill {{ display: inline-block; border-radius: 999px; padding: .1rem .6rem; margin-right: .4rem; font-size: .85rem; }}
.pill.healthy {{ background: #e6f4ea; color: #137333; }}
.pill.watch {{ background: #fef7e0; color: #795809; }}
.pill.sick {{ background: #fce8e6; color: #a50e0e; }}
.pill.unknown {{ background: #f1f3f4; color: #5f6368; }}
.card {{ border: 1px solid #dadce0; border-left: 6px solid; border-radius: 8px; padding: .8rem 1rem; margin: .8rem 0; }}
.card header {{ display: flex; align-items: baseline; gap: .6rem; }}
.card h2 {{ font-size: 1.05rem; margin: 0; flex: 1; }}
.num {{ color: #5f6368; font-variant-numeric: tabular-nums; }}
.badge {{ border-radius: 4px; padding: .1rem .5rem; font-size: .8rem; font-weight: 600; }}
.value {{ font-size: 1.1rem; margin: .5rem 0; }}
.hint {{ font-size: .9rem; color: #444; margin: .25rem 0 .5rem; }}
.start {{ background: #fef7e0; border: 1px solid #f9ab00; border-radius: 8px; padding: .7rem 1rem; }}
.start.ok {{ background: #e6f4ea; border-color: #137333; }}
details {{ font-size: .85rem; color: #444; }}
details code {{ word-break: break-all; white-space: pre-wrap; }}
footer {{ color: #5f6368; font-size: .8rem; margin-top: 2rem; }}
</style>
</head>
<body>
<header class="top">
<h1>digithings readiness</h1>
<p>Computed {stamp} via <code>make readiness</code> — advisory only, never a gate.</p>
<p>{summary}</p>
{start_here}
</header>
<main>
{"".join(cards)}
</main>
<footer>Regenerate: <code>make readiness-html</code> · Detail: <code>make readiness ARGS=--format=json</code> · Bands: <code>docs/agents/READINESS.md</code></footer>
</body>
</html>
"""


def write_doc(table: str) -> None:
    try:
        text = READINESS_DOC.read_text()
    except OSError as exc:
        print(f"{READINESS_DOC} unreadable — not writing ({exc})", file=sys.stderr)
        return
    if BEGIN_MARKER not in text or END_MARKER not in text:
        print(f"{READINESS_DOC} missing markers — not writing", file=sys.stderr)
        return
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    block = f"{BEGIN_MARKER}\n\n_Last computed: {stamp} via `make readiness` (advisory only)._ \n\n{table}\n\n{END_MARKER}"
    new = re.sub(
        f"{re.escape(BEGIN_MARKER)}.*?{re.escape(END_MARKER)}",
        block,
        text,
        count=1,
        flags=re.DOTALL,
    )
    READINESS_DOC.write_text(new)
    print(f"refreshed computed table in {READINESS_DOC}")


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--write", action="store_true", help="refresh computed table in docs/agents/READINESS.md"
    )
    parser.add_argument("--format", choices=["md", "json", "html"], default="md")
    args = parser.parse_args()
    rows = collect()
    stamp = datetime.now(UTC).strftime("%Y-%m-%d %H:%M UTC")
    if args.format == "json":
        print(
            json.dumps(
                [{"dimension": d, "value": v, "band": b, "detail": x} for d, v, b, x in rows],
                indent=2,
            )
        )
    elif args.format == "html":
        print(render_html(rows, stamp))
    else:
        print(render(rows))
    if args.write:
        write_doc(render(rows))
    return 0  # advisory: never fail


if __name__ == "__main__":
    raise SystemExit(main())
