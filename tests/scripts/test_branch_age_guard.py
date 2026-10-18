"""DIG-1578 — the branch-age guard, and the invariant that makes it mean anything.

Two halves, and the second is the load-bearing one.

1. ``scripts/branch_age_guard.py`` buckets remote branches: stale (head over 10
   days, no open PR), open-PR, fresh, excluded. Those tests run the real module
   so an exclusion typo cannot pass by agreeing with another typo.

2. ``test_every_push_trigger_is_branch_filtered`` pins the structural reason the
   guard does not need a skip list. §6.2 item 2 wants a stale branch to stop
   triggering a rebuild. Measured 2026-10-15, no branch without an open PR
   triggers a workflow run at all: every ``on: push`` in ``.github/workflows``
   carries a ``branches:`` or ``tags:`` filter, and the single ``on:
   workflow_run`` is filtered to ``main``. That is what holds the stop.

   It is also the one fact here that nothing else protects. A workflow that adds
   an unfiltered ``push:`` re-bills every stale branch on every push and every
   test in this file still passes, because the guard's own logic is unaffected.
   So the pin is the guard.

Non-vacuity, deliberately explicit: a bucket test that passes on an empty input
proves nothing, so every exclusion arm carries a control name that must NOT be
excluded, and the structural scan asserts it both finds push triggers and
rejects a synthetic unfiltered one.
"""

from __future__ import annotations

import importlib.util
import json
import re
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path
from types import SimpleNamespace

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
GUARD_SCRIPT = REPO_ROOT / "scripts" / "branch_age_guard.py"

NOW = datetime(2026, 10, 15, 12, 0, 0, tzinfo=timezone.utc)


def _load_guard():
    """Import the guard by path; it is a script, not an installed module."""
    spec = importlib.util.spec_from_file_location("branch_age_guard", GUARD_SCRIPT)
    assert spec and spec.loader, "branch_age_guard.py could not be loaded"
    module = importlib.util.module_from_spec(spec)
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


guard = _load_guard()


def branch(name: str, age_days: float) -> dict:
    """A branch payload shaped like the real one, aged by whole days."""
    when = NOW - timedelta(days=age_days)
    return {
        "name": name,
        "commit": {"sha": "deadbeefcafe" * 4},
        "committed_at": when.isoformat().replace("+00:00", "Z"),
    }


# --- Exclusions (policy §6.2) ----------------------------------------------


@pytest.mark.parametrize(
    "name",
    [
        "main",
        "develop",
        "module/digiquant",
        "module/digiquant-work",
        "chore/sync-module-digiquant",
        "release/v1.2.3",
        "DIG-1578-branch-age-guard",
    ],
)
def test_excluded_branch_is_not_stale(name: str) -> None:
    """Every §6.2 exclusion, aged far past the threshold, still lands excluded."""
    census = guard.select_stale([branch(name, 400)], set(), NOW)
    assert census["stale"] == [], f"{name} must not be stale"
    reasons = {e["name"]: e.get("reason", "") for e in census["excluded"]}
    assert name in reasons, f"{name} vanished instead of being excluded"


def test_a_name_that_looks_excluded_but_is_not_is_still_evaluated() -> None:
    """The control: near-miss names must fall through to the age rule.

    Without this, a matcher that excluded every string containing "module"
    would pass every exclusion arm above.
    """
    census = guard.select_stale(
        [branch("task/1234-module-cleanup", 400), branch("releases/v9", 400)],
        set(),
        NOW,
    )
    assert sorted(e["name"] for e in census["stale"]) == [
        "releases/v9",
        "task/1234-module-cleanup",
    ]
    assert len(census["excluded"]) == 0


def test_main_and_develop_are_excluded_even_when_fresh() -> None:
    """Exclusion is not an age fallback — a fresh `develop` is not reported."""
    census = guard.select_stale([branch("develop", 0)], set(), NOW)
    assert census["fresh"] == []
    assert census["excluded"][0]["name"] == "develop"


# --- The 10-day threshold ---------------------------------------------------


def test_exactly_at_the_threshold_is_not_stale() -> None:
    """A 10-day-old head is live until the next second."""
    census = guard.select_stale([branch("task/live", 10)], set(), NOW)
    assert census["stale"] == []
    assert [e["name"] for e in census["fresh"]] == ["task/live"]


def test_just_past_the_threshold_is_stale() -> None:
    census = guard.select_stale([branch("task/dead", 10.01)], set(), NOW)
    assert [e["name"] for e in census["stale"]] == ["task/dead"]


def test_threshold_is_configurable() -> None:
    """A 3-day census must call a 4-day branch stale; the default must not."""
    payload = [branch("task/mid", 4)]
    assert guard.select_stale(payload, set(), NOW)["stale"] == []
    assert [e["name"] for e in guard.select_stale(payload, set(), NOW, 3)["stale"]] == [
        "task/mid"
    ]


def test_a_thirty_day_old_branch_with_no_pr_is_stale() -> None:
    """The acceptance case, named directly."""
    census = guard.select_stale([branch("task/30-day", 30)], set(), NOW)
    entry = census["stale"][0]
    assert entry["name"] == "task/30-day"
    assert entry["age_days"] == 30.0
    assert entry["head_sha"] == "deadbeefcafe"


# --- Open PRs ---------------------------------------------------------------


def test_open_pr_beats_the_age_rule() -> None:
    """An old branch a human is watching is never stale, whatever its age."""
    census = guard.select_stale([branch("task/watched", 300)], {"task/watched"}, NOW)
    assert census["stale"] == []
    entry = census["open_pr"][0]
    assert entry["reason"] == "open PR"


# --- Census integrity -------------------------------------------------------


def test_buckets_reconcile_to_the_input() -> None:
    """A branch that falls out of every bucket is a census that under-reports."""
    payload = [
        branch("main", 100),
        branch("task/a", 40),
        branch("task/b", 2),
        branch("task/c", 40),
        branch("task/nodate", 0),
    ]
    payload[3]["committed_at"] = None
    census = guard.select_stale(payload, {"task/c"}, NOW)
    total = sum(
        len(census[k]) for k in ("stale", "open_pr", "fresh", "excluded")
    )
    assert total == len(payload) == census["total_branches"]


def test_undatable_branch_is_reported_not_dropped() -> None:
    """A branch whose commit date cannot be read is a gap, not a clean result."""
    census = guard.select_stale([{"name": "task/nodate", "commit": {"sha": "x"}}], set(), NOW)
    assert [e["name"] for e in census["excluded"]] == ["task/nodate"]
    assert "commit date unavailable" in census["excluded"][0]["reason"]


def test_empty_input_yields_an_empty_census() -> None:
    """The degenerate arm, so the reconcile test above cannot pass vacuously."""
    census = guard.select_stale([], set(), NOW)
    assert census["total_branches"] == 0
    assert census["stale"] == []


# --- The census that could not be taken --------------------------------------


def test_paged_listing_is_flattened_and_asked_for_correctly(monkeypatch: pytest.MonkeyPatch) -> None:
    """`gh api` paging: `--paginate --slurp`, flattened. Guards the real defect.

    The flag `--paginate-output` does not exist — `gh api` rejects it and the
    script raises, so the guard never reported at all. `gh api --paginate` alone
    emits several JSON documents back to back and does not parse; only `--slurp`
    wraps the pages in one array. Asserted here because nothing else can: the
    branch-count assertions all read 0 if this returns nothing.
    """
    seen: list[list[str]] = []

    def fake_gh(args):
        seen.append(list(args))
        return [
            [{"name": "develop", "commit": {"sha": "a"}}, {"name": "main", "commit": {"sha": "b"}}],
            [{"name": "task/old", "commit": {"sha": "c"}}],
        ]

    monkeypatch.setattr(guard, "_gh", fake_gh)
    rows = guard._gh_rows(["repos", "o/r", "branches"])

    assert [r["name"] for r in rows] == ["develop", "main", "task/old"]
    assert len(rows) == 3, "pages must be flattened, not kept nested"
    argv = seen[0]
    assert "--slurp" in argv, "without --slurp the pages do not parse"
    assert "--paginate" in argv
    assert "--paginate-output" not in argv, "gh api has no such flag"


def test_gh_failure_carries_the_real_reason(monkeypatch: pytest.MonkeyPatch) -> None:
    """The reason must survive into the report; "exit status 1" does not.

    The guard runs unattended, so an operator meets a failure only through the
    report it publishes. gh answers a bad flag with a full usage dump, so only
    the first line is kept — enough to name the cause, short enough to read.
    """
    def fake_run(argv, capture_output, text, check):
        assert capture_output is True and text is True
        return SimpleNamespace(
            returncode=1,
            stdout="",
            stderr="unknown flag: --paginate-output\n\nMakes an authenticated HTTP request.\nmore",
        )

    monkeypatch.setattr(guard.subprocess, "run", fake_run)
    with pytest.raises(RuntimeError) as excinfo:
        guard._gh(["repos/o/r/branches", "--paginate-output"])

    message = str(excinfo.value)
    assert "unknown flag: --paginate-output" in message, message
    assert "Makes an authenticated" not in message, "the usage dump must be trimmed"
    assert "exit status" not in message, "a bare exit status names no cause"


def test_endpoints_are_a_single_argument(monkeypatch: pytest.MonkeyPatch) -> None:
    """`gh api` takes ONE endpoint positional; three is an arity error.

    Measured 2026-10-15: `gh api repos o/r branches` answers "accepts 1 arg(s),
    received 3". The bad `--paginate-output` flag was failing first and hiding
    this one, so the guard had never actually reached the API and its entire
    branch census was untested against a live repo.
    """
    seen: list[list[str]] = []

    def fake_rows(args):
        seen.append(list(args))
        if args[0].endswith("/branches"):
            return [{"name": "develop", "commit": {"sha": "a"}}]
        return [{"head": {"ref": "other"}}]

    monkeypatch.setattr(guard, "_gh_rows", fake_rows)
    monkeypatch.setattr(guard, "_gh", lambda _a: {"commit": {"committer": {"date": None}}})

    guard.fetch_remote_branches("o/r")
    guard.fetch_open_pr_heads("o/r")

    for argv in seen:
        # The endpoint must arrive as ONE element. The defect was
        # ["repos", "o/r", "branches"], which gh reads as three positionals.
        assert "repos" not in argv, f"endpoint split into arguments: {argv}"
        assert argv[0].startswith("repos/"), argv
    assert seen[0][0] == "repos/o/r/branches"
    assert seen[1][0] == "repos/o/r/pulls"
    # A query parameter is "-X GET -f state=open"; `--state open` is not a flag
    # gh api knows, and it fails the whole census.
    assert "state=open" in seen[1]
    assert "--state" not in seen[1]


def test_failed_census_reports_loudly_and_exits_nonzero(
    monkeypatch: pytest.MonkeyPatch, tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    """A census that never ran is NOT zero stale branches.

    The dangerous failure is silence: an unreadable branch list used to exit 0
    with an empty report, which reads exactly like a clean sweep. Three things
    must hold together — the report is loud and non-empty, the exit code is
    non-zero so the dispatch log records a guard that did not run, and the JSON
    carries the error instead of a plausible empty census.
    """
    def boom(_repo):
        raise RuntimeError("gh api failed")

    monkeypatch.setattr(guard, "fetch_remote_branches", boom)
    out = tmp_path / "census.json"
    code = guard.main(["--repo", "o/r", "--json", str(out)])
    printed = capsys.readouterr().out

    assert code == 1, "a failed census must not exit 0; that reads as a clean sweep"
    assert "CENSUS FAILED" in printed
    assert printed.strip(), "an empty report is indistinguishable from zero stale branches"
    payload = json.loads(out.read_text())
    assert "gh api failed" in payload["error"]
    assert payload["stale"] == [] and payload["total_branches"] == 0


def test_failed_census_report_says_no_census_was_taken(monkeypatch) -> None:
    """The report text, read straight off the renderer."""
    report = guard.render_failure("o/r", RuntimeError("gh api failed"))
    assert "CENSUS FAILED" in report
    assert "not** a finding of zero stale branches" in report
    assert report.strip(), "the report must never be empty"
    # A credential must never reach the report.
    assert "Bearer" not in report and "ghp_" not in report


def test_report_names_every_exclusion_family() -> None:
    """The report is the warning; an exclusion nobody can see is not honoured."""
    census = guard.select_stale([branch("task/old", 40), branch("main", 40)], set(), NOW)
    report = guard.render_report(census, "o/r")
    assert "task/old" in report
    for token in ("main", "develop", "module/", "chore/sync-module-", "release/v"):
        assert token in report, f"report does not name the {token} exclusion"
    # The one-line dispatch log identifies itself by job name, which is what
    # makes a census findable in the cron log.
    assert "branch-age-guard" in guard.render_summary_line(census)


# --- The structural pin -----------------------------------------------------


def _push_filter_lines(text: str) -> tuple[bool, list[str]]:
    """``(has_push, filter_lines)`` for the ``on:`` block of a workflow.

    Returns the child lines of ``push:`` so the caller can see whether any
    ``branches:``/``tags:`` key narrows it. An empty filter list under a
    ``push:`` key means the trigger fires on EVERY branch.
    """
    match = re.search(r"^on:\s*$", text, re.M)
    assert match, "workflow has no `on:` block"
    rest = text[match.end() :]
    nxt = re.search(r"^[A-Za-z_]", rest, re.M)
    block = rest[: nxt.start()] if nxt else rest
    lines = block.split("\n")
    has_push = False
    children: list[str] = []
    for i, line in enumerate(lines):
        if re.match(r"^\s{2}push:\s*$", line):
            has_push = True
            indent = len(line) - len(line.lstrip())
            for follow in lines[i + 1 :]:
                if not follow.strip():
                    continue
                if len(follow) - len(follow.lstrip()) <= indent:
                    break
                children.append(follow.strip())
    return has_push, children


UNFILTERED_PUSH = """name: t
on:
  push:
permissions: {}
jobs: {}
"""

FILTERED_PUSH = """name: t
on:
  push:
    branches: [develop]
permissions: {}
jobs: {}
"""


def test_the_push_filter_parser_discriminates() -> None:
    """Non-vacuity for the parser itself: both arms, before it is trusted."""
    has_push, children = _push_filter_lines(UNFILTERED_PUSH)
    assert has_push and children == [], "unfiltered push not detected as unfiltered"
    has_push, children = _push_filter_lines(FILTERED_PUSH)
    assert has_push and children == ["branches: [develop]"], "filter not seen"


def test_every_push_trigger_is_branch_filtered() -> None:
    """The load-bearing pin. No workflow may listen to pushes on every branch.

    This is what makes acceptance item 1 true rather than accidentally true: a
    branch with no open PR starts no run because every push listener is
    narrowed, and this test fails the PR that would widen one.
    """
    offenders: list[str] = []
    seen = 0
    for path in sorted(WORKFLOW_DIR.glob("*.yml")):
        text = path.read_text(encoding="utf-8")
        has_push, children = _push_filter_lines(text)
        if not has_push:
            continue
        seen += 1
        narrowed = any(
            child.startswith(("branches:", "branches-ignore:", "tags:", "tags-ignore:"))
            for child in children
        )
        if not narrowed:
            offenders.append(path.name)
    assert seen >= 5, f"only {seen} push triggers parsed: the scan is wrong"
    assert offenders == [], (
        "workflows that rebuild every branch on push, so stale branches cost CI "
        f"(DIG-1578 §6.2): {offenders}"
    )


def test_the_guard_workflow_is_dispatch_only() -> None:
    """The guard must not reintroduce the clock the repo removed in #3579."""
    text = (WORKFLOW_DIR / "branch-age-guard.yml").read_text(encoding="utf-8")
    block = text.split("on:", 1)[1]
    assert "schedule:" not in block.split("permissions:", 1)[0], (
        "branch-age-guard.yml declares on.schedule; its clock is the cron Worker"
    )
    assert "workflow_dispatch" in block


def test_the_guard_workflow_holds_no_write_scope() -> None:
    """It reports; it performs no write, so it must hold no write permission."""
    text = (WORKFLOW_DIR / "branch-age-guard.yml").read_text(encoding="utf-8")
    perms = text.split("permissions:", 1)[1].split("jobs:", 1)[0]
    assert "write" not in perms, f"the guard must stay read-only, found: {perms.strip()}"


def test_guard_clock_is_registered_on_the_worker() -> None:
    """The clock lives on the Worker, and in both places that must agree.

    ``trigger-contract.test.ts`` asserts ``[triggers].crons`` equals
    ``uniqueEnabledCrons()`` in order; this asserts the row exists at all, so a
    deletion fails here first with a readable message.
    """
    jobs = (REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts").read_text(
        encoding="utf-8"
    )
    assert 'wd("branch-age-guard"' in jobs, "no wd() row for branch-age-guard"
    toml = (REPO_ROOT / "apps" / "digithings-cron" / "wrangler.toml").read_text(
        encoding="utf-8"
    )
    assert "# branch-age-guard" in toml, "no [triggers] crons entry for branch-age-guard"