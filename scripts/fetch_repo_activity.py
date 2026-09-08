#!/usr/bin/env python3
"""Snapshot public repository activity for digithings.ai's repo-activity band.

Why a committed snapshot rather than a live fetch: digithings.ai is
``output: "export"`` — a static export to Cloudflare Pages, so there is no server
at request time, and Cloudflare's build has no GitHub token. The two alternatives
are worse. A client-side fetch is 60 requests/hour per visitor IP unauthenticated,
so on a busy day some visitors would meet an error where the credibility panel
should be. A build-time fetch would need a token in Cloudflare and would fail the
deploy when GitHub is slow.

So this runs in Actions (which already has a token), writes JSON, and commits it.
The band renders a plain object with no network, no loading state and no failure
mode, and the snapshot's own timestamp is printed on the page — the same honesty
`COUNTED_AT` gives the figures on /quality.

WHICH NUMBERS, AND WHY NOT THE OTHERS. Measured 2026-08-06: 770 commits on main and
337 merged PRs in 30 days, against 1 star, 1 fork and 0 watchers. Both are true of
the same repository and they say opposite things. Velocity is the honest signal for
"actively maintained in the open"; a star count on a young repo says only that it is
young. So stars, forks and watchers are deliberately NOT collected — not hidden
after the fact, never fetched, so nobody can wire them in by reading this file and
assuming the field is simply missing.

Open issues ARE collected, and must be rendered near the closed count: 197 alone reads
as backlog debt, while 197 open against 151 closed in a month reads as a backlog being
worked. The owner chose that pairing explicitly. But the two are NOT the same
measurement — see "current state" below — so whatever renders them has to say which
is which. Adjacent, correctly labelled; never merged under one window.

WHAT IS MEASURED WHERE. Three different kinds of number, measured three different
ways. The distinction is load-bearing, and conflating the first two is the defect this
file exists to not have:

* **velocity, windowed** — ``commits``, ``pullsMerged``, ``issuesClosed`` — the last
  30 days on ``main``, the deployed branch (not the repo's GitHub default, which is
  ``develop``). Every one of these queries carries a date bound.
* **current state, NOT windowed** — ``issuesOpen``, ``pullsOpen`` and
  ``latestRelease``. An open issue count is a point in time by nature: "opened in
  the last 30 days and still open" was 30 against a real backlog of 197, and it
  answers a question nobody asked. So these are deliberately unbounded, and any
  surface rendering them must scope them separately from the windowed three. The
  first draft of the band put ``issuesOpen`` inside a ``// last 30 days`` heading,
  which presented a lifetime figure as a monthly one. ``openIssues`` is the same
  unwindowed backlog, sorted by most recently updated, for the detailed list.
* **code shape** — per-module ``files`` and ``lines`` — counted from the local
  checkout at the commit this snapshot is generated at, because the API's tree
  exposes blob *bytes*, never lines.

So the snapshot does not claim one uniform "as of main" for everything, and nothing
here says it does. The page prints ``generatedAt``, which is the honest anchor for
all three.

Usage:
    scripts/fetch_repo_activity.py                      # write the snapshot
    scripts/fetch_repo_activity.py --check              # validate shape, write nothing
    scripts/fetch_repo_activity.py --check --max-age-days 10   # also assert freshness
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
OUT = REPO_ROOT / "frontend" / "digithings-web" / "lib" / "repo-activity.json"
MODULES_TS = REPO_ROOT / "frontend" / "digiweb" / "web" / "src" / "data" / "modules.ts"
SLUG = "digithings-ai/digithings"
WINDOW_DAYS = 30
BRANCH = "main"


def _shown(path: Path) -> str:
    """Repo-relative for readability, absolute when it lies outside the repo.

    `Path.relative_to` *raises* rather than degrading, so formatting an error
    message with it turns a clean "file is missing" report into a ValueError
    traceback the moment OUT is redirected — which is exactly what a test does.
    """
    try:
        return str(path.relative_to(REPO_ROOT))
    except ValueError:
        return str(path)


def _gh(*args: str) -> object:
    out = subprocess.check_output(["gh", *args], text=True, cwd=REPO_ROOT)
    return json.loads(out)


def _since() -> str:
    return (datetime.now(UTC) - timedelta(days=WINDOW_DAYS)).strftime("%Y-%m-%dT%H:%M:%SZ")


def _module_paths() -> dict[str, str]:
    """Registry id -> repo-relative directory, skipping roadmap entries.

    Read from modules.ts rather than hardcoded so a new module is picked up by
    adding it to the registry, which is where every other count already comes from.
    A module that parses but whose directory cannot be found is a hard error, not a
    silent omission — digivault was missing from the registry for months precisely
    because nothing complained about the gap.
    """
    src = MODULES_TS.read_text(encoding="utf-8")
    found = re.findall(r'id: "([a-z]+)",\s*\n\s*name:.*?\n\s*tier: "(\w+)"', src)
    declared = len(re.findall(r'^\s{4}id: "', src, re.MULTILINE))
    if not found:
        raise SystemExit(f"parsed no modules from {MODULES_TS} — has the entry shape changed?")
    # `declared` must be non-zero AND equal. An earlier version read
    # `if declared and ...`, which turned a zero denominator into a pass — so
    # reindenting modules.ts (the `^\s{4}` no longer matching) would disable the very
    # guard meant to catch a module dropping out. Both halves are now loud.
    if len(found) != declared:
        raise SystemExit(
            f"parsed {len(found)} modules from {MODULES_TS} but counted {declared} `id:` "
            "declarations — the regex has drifted from the entry shape; a module would "
            "be silently absent from the activity band"
        )
    paths: dict[str, str] = {}
    missing: list[str] = []
    for mid, tier in found:
        if tier == "roadmap":
            continue  # no directory exists yet; a last-commit date would be a lie
        for cand in (mid, f"frontend/{mid}"):
            if (REPO_ROOT / cand).is_dir():
                paths[mid] = cand
                break
        else:
            missing.append(mid)
    if missing:
        raise SystemExit(
            f"shipping modules with no directory: {', '.join(missing)} — "
            "add the path mapping rather than letting them drop out of the band"
        )
    return paths


def _text_lines(path: Path) -> int:
    """Line count of a tracked text file; 0 for anything binary."""
    try:
        blob = path.read_bytes()
    except OSError:
        return 0
    if b"\0" in blob[:8192]:
        return 0  # image, font, wheel — not code
    return blob.count(b"\n") + (1 if blob and not blob.endswith(b"\n") else 0)


def _code_shape(path: str) -> tuple[int, int]:
    """(files, lines) for tracked text files under *path* in the local checkout."""
    listed = subprocess.check_output(
        ["git", "ls-files", "-z", "--", path], text=False, cwd=REPO_ROOT
    )
    rels = [p.decode("utf-8", "surrogateescape") for p in listed.split(b"\0") if p]
    files = 0
    lines = 0
    for rel in rels:
        n = _text_lines(REPO_ROOT / rel)
        files += 1
        lines += n
    return files, lines


def _commits_since(since: str) -> list[dict]:
    """Every commit on BRANCH since *since*, oldest page last.

    Fetched once and reused: the total is the velocity figure and the subjects are
    where the "newest features" list comes from, so paginating twice would be waste.
    """
    out: list[dict] = []
    page = 1
    while True:
        batch = _gh(
            "api", f"repos/{SLUG}/commits?sha={BRANCH}&since={since}&per_page=100&page={page}"
        )
        if not isinstance(batch, list) or not batch:
            return out
        out.extend(batch)
        if len(batch) < 100:
            return out
        page += 1
        if page > 30:
            print(
                f"⚠️  stopped paginating commits at {len(out)} — the 30-day window is "
                "larger than the 3000-commit cap, so `commits` is a floor, not a total",
                file=sys.stderr,
            )
            return out


# `feat(scope): summary` with an OPTIONAL trailing `(#1930)`. Only `feat` counts as a
# shipped feature; fix/chore/docs/test do not.
#
# The PR number is optional because only a SQUASH merge leaves it in the subject. A
# merge-committed PR keeps its original subjects, unnumbered — and requiring the
# number silently dropped those features while listing older ones above them. PR
# #1911 landed that way with four `feat(digichat)` commits newer than three of the six
# rows this list was showing, which made the page's "the most recent features to land
# on main" false. #1901 is a prior fix for the same merge-vs-squash shape elsewhere.
_FEAT = re.compile(r"^feat(?:\(([^)]+)\))?!?: (.+?)(?:\s*\(#(\d+)\))?$")


def _pr_for_commit(sha: str) -> int | None:
    """The PR a commit arrived in, for subjects that carry no `(#N)`.

    One extra request, and only for commits actually in contention for a row, so the
    cost is a handful of calls rather than one per commit in the window.
    """
    try:
        pulls = _gh("api", f"repos/{SLUG}/commits/{sha}/pulls")
    except subprocess.CalledProcessError:
        return None
    if isinstance(pulls, list) and pulls:
        return int(pulls[0].get("number") or 0) or None
    return None


def _features(commits: list[dict], limit: int = 6) -> list[dict]:
    """Newest shipped features on BRANCH, one row per pull request.

    Deduped by PR: a merge-committed PR contributes several `feat` commits and would
    otherwise fill the whole list by itself. The newest commit's subject represents it.
    A feature with no resolvable PR is skipped — the page states every row is a pull
    request you can open, so a row without one would make that copy false.
    """
    feats: list[dict] = []
    seen: set[int] = set()
    for c in commits:  # the API returns newest first
        subject = ((c.get("commit") or {}).get("message") or "").split("\n", 1)[0]
        m = _FEAT.match(subject)
        if not m:
            continue
        scope, summary, pr_text = m.group(1), m.group(2), m.group(3)
        pr = int(pr_text) if pr_text else _pr_for_commit(c.get("sha") or "")
        if pr is None or pr in seen:
            continue
        seen.add(pr)
        feats.append(
            {
                "scope": scope,
                "summary": summary,
                "pr": pr,
                "date": ((c.get("commit") or {}).get("committer") or {}).get("date"),
            }
        )
        if len(feats) >= limit:
            break
    return feats


def _search_items(payload: object, limit: int) -> list[dict]:
    """Number / title / url rows from a Search issues payload."""
    items = payload.get("items") if isinstance(payload, dict) else None
    if not isinstance(items, list):
        return []
    out: list[dict] = []
    for it in items:
        if not isinstance(it, dict):
            continue
        number = it.get("number")
        title = it.get("title")
        url = it.get("html_url")
        if not isinstance(number, int) or not title or not url:
            continue
        out.append(
            {
                "number": number,
                "title": title,
                "url": url,
                "updatedAt": it.get("updated_at"),
                "closedAt": it.get("closed_at"),
            }
        )
        if len(out) >= limit:
            break
    return out


def collect() -> dict:
    since = _since()
    commits = _commits_since(since)

    merged = _gh(
        "api",
        f"search/issues?q=repo:{SLUG}+is:pr+is:merged+merged:>={since[:10]}&per_page=6&sort=updated",
    )
    closed = _gh(
        "api",
        f"search/issues?q=repo:{SLUG}+is:issue+is:closed+closed:>={since[:10]}&per_page=1",
    )
    # Deliberately UNBOUNDED, unlike the three above — the whole open backlog, not
    # what opened this month. Consumers must label it as current state; see the
    # module docstring.
    #
    # And NOT repo.open_issues_count: GitHub models PRs as issues, so that field is
    # open issues PLUS open PRs. Measured 2026-08-06 it read 203 against a true
    # 197 issues + 6 open PRs. This renders beside `issuesClosed`, which comes from
    # `is:issue`, and a pair whose halves are scoped differently is a false figure on
    # a page that promises "every figure is countable in the repo".
    open_issues = _gh(
        "api",
        f"search/issues?q=repo:{SLUG}+is:issue+is:open&per_page=6&sort=updated",
    )
    open_prs = _gh(
        "api",
        f"search/issues?q=repo:{SLUG}+is:pr+is:open&per_page=1",
    )

    releases = _gh("api", f"repos/{SLUG}/releases?per_page=1")
    latest = releases[0] if isinstance(releases, list) and releases else None

    modules = {}
    for mid, path in _module_paths().items():
        hist = _gh("api", f"repos/{SLUG}/commits?path={path}&sha={BRANCH}&per_page=1")
        last = None
        if isinstance(hist, list) and hist:
            last = (hist[0].get("commit") or {}).get("committer", {}).get("date")
        files, lines = _code_shape(path)
        modules[mid] = {"path": path, "lastCommit": last, "files": files, "lines": lines}

    return {
        "generatedAt": datetime.now(UTC).strftime("%Y-%m-%dT%H:%M:%SZ"),
        "windowDays": WINDOW_DAYS,
        "commits": len(commits),
        "features": _features(commits),
        "pullsMerged": int(merged.get("total_count", 0)) if isinstance(merged, dict) else 0,
        "issuesClosed": int(closed.get("total_count", 0)) if isinstance(closed, dict) else 0,
        "pullsOpen": int(open_prs.get("total_count", 0)) if isinstance(open_prs, dict) else 0,
        "issuesOpen": int(open_issues.get("total_count", 0))
        if isinstance(open_issues, dict)
        else 0,
        "mergedPulls": [
            {
                "number": row["number"],
                "title": row["title"],
                "url": row["url"],
                "mergedAt": row["closedAt"],
            }
            for row in _search_items(merged, 6)
        ],
        "openIssues": [
            {
                "number": row["number"],
                "title": row["title"],
                "url": row["url"],
                "updatedAt": row["updatedAt"],
            }
            for row in _search_items(open_issues, 6)
        ],
        "branch": BRANCH,
        "latestRelease": (
            {
                "tag": latest.get("tag_name"),
                "name": latest.get("name"),
                "publishedAt": latest.get("published_at"),
                "url": latest.get("html_url"),
            }
            if latest
            else None
        ),
        "modules": modules,
    }


REQUIRED = (
    "generatedAt",
    "commits",
    "pullsMerged",
    "issuesClosed",
    "pullsOpen",
    "issuesOpen",
    "features",
    "mergedPulls",
    "openIssues",
    "modules",
)
# Never collected — see the module docstring. Asserted so a future edit that adds
# them has to delete this line and read why first.
FORBIDDEN = ("stars", "stargazers", "forks", "watchers", "subscribers")


def check(max_age_days: int | None = None) -> int:
    """Validate the committed snapshot.

    Shape is always checked, and test-web.yml runs this bare form on every website PR.
    Freshness is checked only when *max_age_days* is given, and that asymmetry is
    deliberate: a hard staleness gate on that lane would turn "the refresh cron did not
    run" into a red build on unrelated work, which is exactly the kind of unrelated-red
    that gets a check disabled. Staleness is surfaced where it belongs instead — the
    page prints the snapshot's own date, so an old snapshot looks old to a reader
    rather than blocking a deploy. Only the refresh workflow passes --max-age-days, to
    assert the output it just generated is current.
    """
    if not OUT.exists():
        print(f"❌  {_shown(OUT)} is missing — run this script", file=sys.stderr)
        return 1
    try:
        data = json.loads(OUT.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"❌  {_shown(OUT)} is not valid JSON: {exc}", file=sys.stderr)
        return 1
    for key in REQUIRED:
        if key not in data:
            print(f"❌  snapshot is missing {key!r}", file=sys.stderr)
            return 1
    for key in FORBIDDEN:
        if key in data:
            print(
                f"❌  snapshot carries {key!r} — vanity metrics are deliberately not "
                "collected; read the docstring before adding one",
                file=sys.stderr,
            )
            return 1
    if not isinstance(data["modules"], dict) or not data["modules"]:
        print("❌  snapshot has no per-module activity", file=sys.stderr)
        return 1
    if not isinstance(data["mergedPulls"], list) or not isinstance(data["openIssues"], list):
        print("❌  mergedPulls and openIssues must be lists", file=sys.stderr)
        return 1
    try:
        stamped = datetime.strptime(data["generatedAt"], "%Y-%m-%dT%H:%M:%SZ").replace(tzinfo=UTC)
    except ValueError as exc:
        print(f"❌  generatedAt is not an ISO-Z timestamp: {exc}", file=sys.stderr)
        return 1
    age = datetime.now(UTC) - stamped
    if max_age_days is not None and age > timedelta(days=max_age_days):
        print(
            f"❌  snapshot is {age.days} days old (limit {max_age_days})",
            file=sys.stderr,
        )
        return 1
    print(f"repo activity: {age.days}d old, {len(data['modules'])} modules ✅")
    return 0


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--check", action="store_true", help="validate the snapshot, write nothing")
    parser.add_argument(
        "--max-age-days",
        type=int,
        default=None,
        help="with --check, also fail when the snapshot is older than this",
    )
    args = parser.parse_args()
    if args.check:
        return check(args.max_age_days)

    data = collect()
    OUT.write_text(json.dumps(data, indent=2) + "\n", encoding="utf-8")
    print(f"wrote {_shown(OUT)}")
    print(f"  {data['commits']} commits / {data['windowDays']}d on {data['branch']}")
    print(f"  {data['pullsMerged']} PRs merged, {data['issuesClosed']} issues closed")
    print(f"  {data['pullsOpen']} PRs open, {data['issuesOpen']} issues open")
    for p in data["mergedPulls"]:
        print(f"  merged #{p['number']}: {p['title'][:56]}")
    for issue in data["openIssues"]:
        print(f"  open #{issue['number']}: {issue['title'][:56]}")
    rel = data["latestRelease"]
    print(f"  latest release: {rel['tag']} ({rel['publishedAt'][:10]})" if rel else "  no releases")
    for f in data["features"]:
        print(f"  feat #{f['pr']}: {f['scope'] or '-'} — {f['summary'][:56]}")
    for mid, m in data["modules"].items():
        print(
            f"    {mid:11} {m['files']:>4} files {m['lines']:>7} lines  "
            f"last {(m['lastCommit'] or '?')[:10]}"
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
