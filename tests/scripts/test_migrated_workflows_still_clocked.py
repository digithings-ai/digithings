"""Pin the second half of the GHA clock cutover: develop has no clock, and
the Cloudflare cron that replaced it is still there.

``test_no_gha_schedules.py`` (#4971, commit 8540d815) pins one direction only:
no workflow on ``develop`` declares ``on.schedule``. That is the "disable".
It says nothing about the "port": if a Cloudflare cron row were deleted from
``apps/digithings-cron/src/jobs.ts``, every migrated workflow would silently
become a manual-dispatch orphan and the cutover would still look complete.

This module pins the pair. Each workflow the migration de-clocked must still
be clocked by an ENABLED Worker job, and the workflow file must still exist on
``develop`` so the Worker has something to dispatch.

Why the table is a snapshot and not a derivation:

* The list is literal and dated on purpose. Deriving it from ``jobs.ts`` at test
  time would make the pin tautological: it would agree with whatever the file
  currently says. A snapshot fails when a clock disappears, which is the point.
* Only digithings-owned workflows are pinned. ``jobs.ts`` also carries
  ``twelve-x-*`` rows whose target workflows live in digithings-ai/twelve-x (the
  dispatch repo is overridable per row) plus ``smoke-*`` probe rows. Those target
  names are absent from ``.github/workflows`` here by design, so an existence
  check over every row would be a wrong invariant.
* Re-pointing a clock at a different job id, disabling it, or renaming it is a
  behaviour change. Update this table in the same commit that makes it.

Measured 2026-10-14 at develop d227b6ed5 (DIG-3605).
"""

from __future__ import annotations

import re
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW_DIR = REPO_ROOT / ".github" / "workflows"
JOBS_SOURCE = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"

# Every builder that names a workflow in jobs.ts. A builder missing here is
# invisible to the parse, which would leave its row unpinned while the pins below
# still pass, so test_worker_clock_rows_are_parsed_completely fails instead.
# At develop d227b6ed5 the file used cj, pj, tw and wd. rd and wj are kept
# because the house parity mirror in test_prices_cron_dst.py names them, and an
# unused entry costs nothing: the guard fails on a builder present here and
# absent from this tuple, never on the reverse.
BUILDERS = ("wd", "rd", "cj", "pj", "wj", "tw")

# workflow file -> job id(s) in jobs.ts that must carry its clock, enabled.
MIGRATED_CLOCKS: dict[str, tuple[str, ...]] = {
    "agent-backlog-snapshot.yml": ("agent-backlog-snapshot",),
    "pipeline-continuous-improvement.yml": ("continuous-improvement",),
    "pipeline-maintenance.yml": ("maintenance",),
    "pipeline-provider-review.yml": ("provider-review",),
    "pipeline-dependency-freshness.yml": ("dependency-freshness",),
    "refresh-repo-activity.yml": ("refresh-repo-activity",),
    "openwiki-update.yml": ("openwiki-update",),
    "token-canary.yml": ("token-canary",),
    "secret-staleness-check.yml": ("secret-staleness",),
    "datatap-answer-check.yml": ("datatap-answer-check",),
    "production-deploy-gate-watchdog.yml": ("production-deploy-gate-watchdog",),
    "pipeline-checkpoint-archive.yml": ("checkpoint-archive",),
    "pipeline-market-data-refresh.yml": (
        "market-data-refresh-morning",
        "market-data-refresh-evening",
    ),
    "pipeline-digiquant.yml": ("house-run-09",),
    "project-enforce-assignment.yml": ("project-enforce-assignment",),
}

_CALL = re.compile(r"\b([A-Za-z_][A-Za-z0-9_]*)\s*\(")
_YML = re.compile(r'"[^"]+\.yml"')


def _calls(text: str):
    """Yield ``(name, args_text, span)`` for every call that names a workflow.

    A call is a candidate when its argument text contains a quoted ``.yml``
    string. The builder name is not part of the test, so a builder added to
    jobs.ts later cannot hide from this scan. Nested calls are skipped once
    their outermost enclosing call has been counted.
    """
    counted: list[tuple[int, int]] = []
    for match in _CALL.finditer(text):
        start, depth, end = match.end(), 1, match.end()
        while end < len(text) and depth:
            if text[end] == "(":
                depth += 1
            elif text[end] == ")":
                depth -= 1
            end += 1
        args = text[start : end - 1]
        if not _YML.search(args):
            continue
        if any(lo <= match.start() < hi for lo, hi in counted):
            continue
        counted.append((match.start(), end))
        yield match.group(1), args


def _job_rows() -> tuple[list[dict[str, object]], set[str], int]:
    """Parse jobs.ts into ``(rows, builder_names, target_count)``."""
    rows: list[dict[str, object]] = []
    names: set[str] = set()
    targets = 0
    for name, args in _calls(JOBS_SOURCE.read_text(encoding="utf-8")):
        targets += 1
        names.add(name)
        strings = re.findall(r'"([^"]*)"', args)
        if name not in BUILDERS or len(strings) < 3 or not strings[2].endswith(".yml"):
            continue
        rows.append(
            {
                "id": strings[0],
                "cron": strings[1],
                "workflow": strings[2],
                "enabled": "enabled: false" not in args,
            }
        )
    return rows, names, targets


@pytest.fixture(scope="module")
def parsed() -> tuple[list[dict[str, object]], set[str], int]:
    return _job_rows()


@pytest.fixture(scope="module")
def rows(parsed) -> list[dict[str, object]]:
    return parsed[0]


def test_worker_clock_rows_are_parsed_completely(
    rows: list[dict[str, object]], parsed: tuple[list[dict[str, object]], set[str], int]
) -> None:
    """Non-vacuity: the parse sees every clock row there is.

    A row the parse skips leaves its workflow unpinned while the pin below
    still passes. So every call naming a workflow is counted without looking at
    builder names, and the builders seen must all be known here.
    """
    _row_list, names, targets = parsed
    unknown = sorted(names - set(BUILDERS))
    assert unknown == [], f"jobs.ts gained clock builders this module cannot parse: {unknown}"
    assert targets > 40, f"only {targets} workflow-targeting calls found: the scan is wrong"
    assert len(rows) == targets, f"parsed {len(rows)} rows of {targets} clock rows"
    assert any(r["id"] == "checkpoint-archive" for r in rows), (
        "known-present control job id not parsed: the matcher cannot discriminate"
    )


def test_migrated_workflows_are_still_clocked(rows: list[dict[str, object]]) -> None:
    """Every de-clocked workflow still has an ENABLED Worker clock."""
    by_id = {str(r["id"]): r for r in rows}
    missing: list[str] = []
    disabled: list[str] = []
    for workflow, job_ids in MIGRATED_CLOCKS.items():
        for job_id in job_ids:
            row = by_id.get(job_id)
            if row is None or row["workflow"] != workflow:
                missing.append(f"{workflow} -> {job_id}")
            elif not row["enabled"]:
                disabled.append(f"{workflow} -> {job_id}")
    assert missing == [], f"migrated clocks lost from jobs.ts: {missing}"
    assert disabled == [], f"migrated clocks left disabled in jobs.ts: {disabled}"


def test_clock_lookup_discriminates(rows: list[dict[str, object]]) -> None:
    """A name that is not a clock must not resolve.

    Without this, a matcher that matched everything would pass the pin above.
    """
    known = {str(r["workflow"]) for r in rows}
    assert "this-workflow-does-not-exist.yml" not in known
    assert "pipeline-digiquant-prices.yml" in known, (
        "control: a real digithings workflow must be visible to the same lookup"
    )


def test_migrated_workflow_files_still_exist() -> None:
    """The Worker must have something on develop to dispatch for each pin."""
    present = {p.name for p in WORKFLOW_DIR.iterdir() if p.is_file()}
    assert len(present) > 40, f"workflow directory census looks truncated: {len(present)}"
    absent = sorted(set(MIGRATED_CLOCKS) - present)
    assert absent == [], f"pinned workflows are gone from develop: {absent}"
