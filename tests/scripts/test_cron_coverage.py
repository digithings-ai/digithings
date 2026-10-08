"""Unit tests for scripts/check_cron_coverage.py (DIG-217).

DIG-217 was a 3.3-day hole in which no clock fired and nothing noticed: the
session-catchup workflow's schedule produced no runs at all, and no check asked
whether a workflow that was due actually ran. These tests pin the verdicts that
would have caught it, and pin the two ways this check could otherwise lie:

* work was due and zero runs exist is always a failure, never absorbed by the
  tolerance (that is the DIG-217 signature);
* a market-gated job cannot fail, because a holiday and a dropped dispatch are
  indistinguishable without a trading calendar;
* several clocks share one workflow, and GitHub cannot say which cron made a
  run — so the verdict is taken on the group. The regression test below kills
  one clock and asserts the check still notices; the pre-fix per-clock count
  reported ok.
"""

from __future__ import annotations

import importlib.util
import json
import sys
from datetime import datetime, timedelta, timezone
from pathlib import Path

import pytest

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "scripts" / "check_cron_coverage.py"
JOBS_TS = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"


def _load_module():
    spec = importlib.util.spec_from_file_location("check_cron_coverage_under_test", SCRIPT)
    assert spec and spec.loader
    module = importlib.util.module_from_spec(spec)
    # dataclasses resolve their own module through sys.modules, so register
    # before exec.
    sys.modules[spec.name] = module
    spec.loader.exec_module(module)
    return module


cron_coverage = _load_module()


def _utc(text: str) -> datetime:
    return cron_coverage.parse_iso_utc(text)


# The window used throughout: Sun 2026-10-04T12:00Z -> Tue 2026-10-06T12:00Z.
# Two full weekdays plus a partial one, so it holds both a 24h/5d clock and a
# multi-hourly one.
START = _utc("2026-10-04T12:00:00Z")
END = _utc("2026-10-06T12:00:00Z")


def _job(**kwargs):
    base = {
        "id": "j",
        "cron": "0 0 * * *",
        "repo": "digithings-ai/digithings",
        "kind": "workflow_dispatch",
        "workflow": "w.yml",
        "et_open_gate": False,
    }
    base.update(kwargs)
    return cron_coverage.ExpectedJob(**base)


def _observed(seen: int, newest: str = "2026-10-05T00:00:00Z"):
    return cron_coverage.Observed(seen=seen, newest_run=newest if seen else None)


# --------------------------------------------------------------------------
# cron expansion
# --------------------------------------------------------------------------


@pytest.mark.parametrize(
    ("expr", "expected"),
    [
        # The clock DIG-217 lost. Mon is 24 hourly ticks, Tue contributes the
        # hours before the window closes.
        ("52 * * * MON-FRI", 36),
        ("8 7 * * SAT", 0),  # the Saturday before the window opens
        ("8 22 * * SUN", 1),  # Sunday inside the window
        ("7,22,37,52 13-21 * * MON-FRI", 36),  # Mon 13..21 is 9 hours x 4
        ("19 */2 * * MON-FRI", 18),  # every 2nd hour, Mon 00..22
        ("3 6,18 * * *", 4),  # Sun 18, Mon 6 + 18, Tue 6
        ("15 12 * * *", 2),  # Tue 12:15 is the end instant, excluded
        ("40 13 * * MON-FRI", 1),
    ],
)
def test_expected_runs_counts_due_ticks(expr, expected):
    assert cron_coverage.expected_runs(expr, START, END) == expected


def test_day_of_month_and_day_of_week_are_ored_not_anded():
    """Vixie semantics: when both dom and dow are restricted, either can match.

    Getting this wrong would silently halve the expectation for any clock that
    pins a date as well as a weekday.
    """
    spec = cron_coverage.parse_cron("0 12 15 * MON")
    # 15 Oct 2026 is a Thursday, so the 15th alone would count 0 under AND.
    assert spec.matches(datetime(2026, 10, 15, 12, tzinfo=timezone.utc)) is True
    # Every Monday is due even though the dom does not match.
    assert spec.matches(datetime(2026, 10, 5, 12, tzinfo=timezone.utc)) is True
    # A non-Monday outside the 15th is not.
    assert spec.matches(datetime(2026, 10, 6, 12, tzinfo=timezone.utc)) is False


@pytest.mark.parametrize(
    "expr",
    ["", "not a cron", "* * *", "99 * * * *", "0 0 0 * *", "0 0 * * FUNDAY", "*/0 * * * *"],
)
def test_unparseable_cron_is_rejected(expr):
    with pytest.raises(cron_coverage.CronError):
        cron_coverage.parse_cron(expr)


def test_window_bounds_are_half_open():
    """A tick at exactly the window start is counted; one at the end is not.

    `CronSpec.matches` answers "does this instant match", with no window; the
    boundary rule lives in the counting, so that is what is pinned here.
    """
    start = datetime(2026, 10, 5, 12, 0, tzinfo=timezone.utc)
    end = start + timedelta(hours=1)
    assert cron_coverage.expected_runs("0 12 * * *", start, end) == 1
    # Sliding the window past that tick removes it.
    assert (
        cron_coverage.expected_runs(
            "0 12 * * *", start + timedelta(minutes=1), end + timedelta(minutes=1)
        )
        == 0
    )


# --------------------------------------------------------------------------
# timestamps
# --------------------------------------------------------------------------


def test_parse_iso_utc_accepts_z_and_offsets_and_normalises():
    assert _utc("2026-10-06T12:00:00Z") == datetime(
        2026, 10, 6, 12, tzinfo=timezone.utc
    )
    assert _utc("2026-10-06T14:00:00+02:00") == datetime(
        2026, 10, 6, 12, tzinfo=timezone.utc
    )
    # A naive stamp is UTC by convention here, not a local-time bug.
    assert _utc("2026-10-06T12:00:00") == datetime(
        2026, 10, 6, 12, tzinfo=timezone.utc
    )


def test_parse_iso_utc_rejects_nonsense():
    with pytest.raises(ValueError):
        _utc("yesterday")


# --------------------------------------------------------------------------
# reading the clock out of jobs.ts
# --------------------------------------------------------------------------


def test_parses_the_real_job_map():
    jobs = cron_coverage.parse_jobs_ts(JOBS_TS)
    by_id = {j.id: j for j in jobs}

    # The clock that vanished for 3.3 days.
    catchup = by_id["twelve-x-session-catchup"]
    assert catchup.cron == "52 * * * MON-FRI"
    assert catchup.repo == "digithings-ai/twelve-x"
    assert catchup.kind == "workflow_dispatch"
    assert catchup.workflow == "session_catchup.yml"
    assert catchup.et_open_gate is False

    # A repository_dispatch clock: the 4th positional is an event_type, not a
    # workflow path, and must not be reported as one.
    house = by_id["house-run-09"]
    assert house.kind == "repository_dispatch"
    assert house.workflow is None
    assert house.target == "repository_dispatch"
    assert house.repo == "digithings-ai/digithings"

    # The option object has to be read, not just the positionals.
    assert by_id["prices-at-open-13"].et_open_gate is True
    assert by_id["prices-intraday"].et_open_gate is False
    assert by_id["maintenance"].et_open_gate is False


def test_the_job_map_still_agrees_with_wrangler_triggers():
    """Every enabled clock must also be a deployed trigger.

    A job in jobs.ts with no matching cron in wrangler.toml never fires, and
    would show up as a permanent missing run. This is the check that keeps the
    two sources of truth from drifting.
    """
    toml = (REPO_ROOT / "apps" / "digithings-cron" / "wrangler.toml").read_text()
    crons = _wrangler_crons(toml)
    jobs = cron_coverage.parse_jobs_ts(JOBS_TS)
    missing = {j.id: j.cron for j in jobs if j.cron not in crons}
    assert not missing, f"jobs.ts clocks absent from wrangler [triggers]: {missing}"


def _wrangler_crons(toml: str) -> set:
    """The quoted entries of `[triggers] crons`, whatever their weekday names.

    The header is matched at the start of a line: the file's comment above the
    section also mentions "[triggers]", so a plain substring split lands on the
    comment and silently yields the wrong block.
    """
    import re

    section = re.split(r"^\[triggers\]\s*$", toml, maxsplit=1, flags=re.M)[1]
    block = re.split(r"^\[", section, maxsplit=1, flags=re.M)[0]
    return set(re.findall(r'"([^"]+)"', block))


def test_function_declarations_are_not_mistaken_for_calls(tmp_path):
    """`function wd(id: string, ...)` must not parse as a job.

    The naive `wd(` pattern matches the declaration too, which is how a
    declaration-only parse used to produce two phantom rows.
    """
    source = (JOBS_TS).read_text(encoding="utf-8")
    jobs = cron_coverage.parse_jobs_ts(JOBS_TS)
    assert not any(j.id in {"id", "string"} for j in jobs)
    # Sanity: the declarations really are in the file we parsed.
    assert "function wd(" in source


def test_disabled_job_is_excluded(tmp_path):
    src = tmp_path / "jobs.ts"
    src.write_text(
        """
const DIGITHINGS = "digithings-ai/digithings" as const;
function wd(id: string, cron: string, repo: string, workflow: string, opts = {}): Job {
  return { id, cron, repo, workflow, opts } as unknown as Job;
}
export const JOBS: readonly Job[] = [
  wd("live", "0 1 * * *", DIGITHINGS, "live.yml"),
  wd("off", "0 2 * * *", DIGITHINGS, "off.yml", { enabled: false }),
];
""",
        encoding="utf-8",
    )
    jobs = cron_coverage.parse_jobs_ts(src)
    assert [j.id for j in jobs] == ["live"]


def test_unknown_repo_constant_is_refused(tmp_path):
    src = tmp_path / "jobs.ts"
    src.write_text(
        """
const DIGITHINGS = "digithings-ai/digithings" as const;
function wd(id: string, cron: string, repo: string, workflow: string, opts = {}): Job {
  return { id, cron, repo, workflow, opts } as unknown as Job;
}
export const JOBS: readonly Job[] = [
  wd("live", "0 1 * * *", SOME_UNDECLARED_REPO, "live.yml"),
];
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="unknown repo constant"):
        cron_coverage.parse_jobs_ts(src)


def test_duplicate_job_id_is_refused(tmp_path):
    src = tmp_path / "jobs.ts"
    src.write_text(
        """
const DIGITHINGS = "digithings-ai/digithings" as const;
function wd(id: string, cron: string, repo: string, workflow: string, opts = {}): Job {
  return { id, cron, repo, workflow, opts } as unknown as Job;
}
export const JOBS: readonly Job[] = [
  wd("twice", "0 1 * * *", DIGITHINGS, "a.yml"),
  wd("twice", "0 2 * * *", DIGITHINGS, "b.yml"),
];
""",
        encoding="utf-8",
    )
    with pytest.raises(ValueError, match="duplicate job id"):
        cron_coverage.parse_jobs_ts(src)


def test_empty_job_map_is_refused(tmp_path):
    src = tmp_path / "jobs.ts"
    src.write_text("export const JOBS: readonly Job[] = [];\n", encoding="utf-8")
    with pytest.raises(ValueError, match="no enabled jobs"):
        cron_coverage.parse_jobs_ts(src)


# --------------------------------------------------------------------------
# the verdicts
# --------------------------------------------------------------------------


def test_due_but_zero_runs_fails_whatever_the_tolerance():
    """The DIG-217 case, and the reason tolerance is not applied here."""
    job = _job()
    for tolerance in (0, 1, 5, 100):
        row = cron_coverage.classify(job, 36, _observed(0), tolerance)
        assert row.status == cron_coverage.STATUS_MISSING
        assert row.fails is True


def test_short_beyond_tolerance_is_degraded():
    row = cron_coverage.classify(_job(), 36, _observed(34), 1)
    assert row.status == cron_coverage.STATUS_DEGRADED
    assert row.fails is True


def test_short_within_tolerance_is_ok():
    row = cron_coverage.classify(_job(), 36, _observed(35), 1)
    assert row.status == cron_coverage.STATUS_OK
    assert row.fails is False


def test_market_gated_missing_is_reported_but_never_fails():
    """A holiday looks exactly like a dropped dispatch; the check cannot know."""
    row = cron_coverage.classify(_job(et_open_gate=True), 1, _observed(0), 1)
    assert row.status == cron_coverage.STATUS_GATED
    assert row.fails is False
    assert "market-gated" in row.note


def test_market_gated_partial_still_fails():
    """Gating covers the blackout case only, and that is deliberate.

    A gated job with *some* runs is reporting, so the Worker is demonstrably
    dispatching; only a total absence is ambiguous between a market holiday and
    a dropped clock. Letting a half-delivered market clock pass silently is the
    failure mode worth more than the holiday noise tolerance already buys.
    """
    row = cron_coverage.classify(_job(et_open_gate=True), 5, _observed(1), 0)
    assert row.status == cron_coverage.STATUS_DEGRADED
    assert row.fails is True


def test_not_due_in_the_window_is_skipped():
    row = cron_coverage.classify(_job(), 0, _observed(0), 1)
    assert row.status == cron_coverage.STATUS_SKIPPED
    assert row.fails is False


def test_probe_error_is_unknown_not_a_verdict():
    """A failed read must never be reported as a coverage failure."""
    err = cron_coverage.Observed(error="gh: HTTP 503")
    row = cron_coverage.classify(_job(), 36, err, 1)
    assert row.status == cron_coverage.STATUS_PROBE_ERROR
    assert row.fails is False
    assert "503" in row.note


def test_failing_statuses_are_exactly_missing_and_degraded():
    assert cron_coverage.FAILING_STATUSES == {
        cron_coverage.STATUS_MISSING,
        cron_coverage.STATUS_DEGRADED,
    }


# --------------------------------------------------------------------------
# clocks that share a workflow
# --------------------------------------------------------------------------


def test_one_dead_clock_inside_a_shared_workflow_is_still_caught():
    """Regression: six clocks dispatch pipeline-digiquant-prices.yml.

    GitHub reports runs for the workflow, not for the cron that started them.
    Counting each clock against that shared total let a dead clock hide inside
    its five siblings' runs: intraday stops, the total still clears every other
    clock's expectation, and the check said ok. The verdict has to be taken on
    the group.
    """
    jobs = [
        _job(id="a", cron="0 1 * * *", workflow="shared.yml"),
        _job(id="b", cron="0 2 * * *", workflow="shared.yml"),
        _job(id="c", cron="0 3 * * *", workflow="shared.yml"),
    ]
    start = _utc("2026-10-05T00:00:00Z")
    end = _utc("2026-10-06T00:00:00Z")
    key = ("digithings-ai/digithings", "workflow_dispatch", "shared.yml")

    # All three alive: one run each, group total 3.
    healthy = cron_coverage.build_rows(jobs, {key: _observed(3)}, start, end, 0)
    assert {r.status for r in healthy} == {cron_coverage.STATUS_OK}

    # Clock `c` dies: only 2 runs for a group expectation of 3.
    degraded = cron_coverage.build_rows(jobs, {key: _observed(2)}, start, end, 0)
    assert {r.status for r in degraded} == {cron_coverage.STATUS_DEGRADED}
    assert any(r.fails for r in degraded)
    # The report must still attribute the shortfall to the shared group.
    assert "sharing this workflow" in next(r for r in degraded if r.fails).note

    # Whole target dark: the DIG-217 signature, three clocks, zero runs.
    dark = cron_coverage.build_rows(jobs, {key: _observed(0)}, start, end, 0)
    assert {r.status for r in dark} == {cron_coverage.STATUS_MISSING}
    assert all(r.fails for r in dark)


def test_shared_rows_keep_their_own_expectation_for_the_reader():
    jobs = [
        _job(id="hourly", cron="0 * * * *", workflow="shared.yml"),
        _job(id="weekly", cron="0 3 * * SUN", workflow="shared.yml"),
    ]
    start = _utc("2026-10-05T00:00:00Z")  # a Monday
    end = _utc("2026-10-06T00:00:00Z")
    rows = cron_coverage.build_rows(jobs, {}, start, end, 1)
    by_id = {r.job.id: r for r in rows}
    assert by_id["hourly"].expected == 24
    assert by_id["weekly"].expected == 0
    assert by_id["hourly"].group_expected == 24
    assert by_id["hourly"].shared is True
    assert by_id["hourly"].compared_against == 24


def test_an_unprobed_target_is_not_a_failure():
    jobs = [_job()]
    rows = cron_coverage.build_rows(jobs, {}, START, END, 1)
    assert rows[0].status == cron_coverage.STATUS_PROBE_ERROR
    assert rows[0].fails is False


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def _row(**kwargs):
    job = _job(id=kwargs.pop("id", "j"), cron=kwargs.pop("cron", "0 0 * * *"))
    return cron_coverage.classify(job, kwargs.pop("expected", 1), _observed(0), 1, **kwargs)


def test_markdown_names_the_failing_clock_and_the_window():
    rows = [_row(id="twelve-x-session-catchup", expected=36)]
    md = cron_coverage.render_markdown(rows, START, END, api_calls=3)
    assert "twelve-x-session-catchup" in md
    assert "2026-10-04T12:00:00Z" in md and "2026-10-06T12:00:00Z" in md
    assert "GitHub API calls: **3**" in md


def test_markdown_explains_the_group_qualifier():
    jobs = [
        _job(id="a", cron="0 1 * * *", workflow="shared.yml"),
        _job(id="b", cron="0 2 * * *", workflow="shared.yml"),
    ]
    start = _utc("2026-10-05T00:00:00Z")
    end = _utc("2026-10-06T00:00:00Z")
    rows = cron_coverage.build_rows(jobs, {}, start, end, 0)
    md = cron_coverage.render_markdown(rows, start, END, api_calls=2)
    assert "own of group" in md


def test_text_report_summarises_the_failing_count():
    dead = _row(id="dead")
    alive = cron_coverage.classify(_job(id="fine"), 2, _observed(2), 1)
    out = cron_coverage.render_text([dead, alive], START, END)
    assert "1 failing of 2 jobs" in out
    assert "dead" in out
    assert "fine" in out


def test_json_verdict_carries_the_machine_readable_fields():
    rows = [_row(id="dead", expected=36)]
    payload = {
        "failing": [r.to_dict() for r in rows if r.fails],
        "jobs": [r.to_dict() for r in rows],
    }
    assert payload["failing"][0]["id"] == "dead"
    assert payload["failing"][0]["expected"] == 36
    assert payload["failing"][0]["fails"] is True


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def test_plan_only_needs_no_token_and_no_network(capsys):
    rc = cron_coverage.main(["--plan-only", "--json", "--now", "2026-10-06T12:00:00Z"])
    assert rc == cron_coverage.OK
    payload = json.loads(capsys.readouterr().out)
    ids = {j["id"] for j in payload["jobs"]}
    assert "twelve-x-session-catchup" in ids
    assert payload["window_end"].startswith("2026-10-06T12:00")


def test_plan_only_text_lists_every_clock(capsys):
    rc = cron_coverage.main(["--plan-only", "--now", "2026-10-06T12:00:00Z"])
    assert rc == cron_coverage.OK
    out = capsys.readouterr().out
    assert "twelve-x-session-catchup" in out


def test_a_broken_now_is_a_probe_error_not_a_crash(capsys):
    rc = cron_coverage.main(["--plan-only", "--now", "not-a-timestamp"])
    assert rc == cron_coverage.PROBE_ERROR
    assert "ISO-8601" in capsys.readouterr().err


def test_an_unreadable_job_map_is_a_probe_error(tmp_path, capsys):
    rc = cron_coverage.main(["--plan-only", "--jobs-ts", str(tmp_path / "absent.ts")])
    assert rc == cron_coverage.PROBE_ERROR
    assert "cannot read the job clock" in capsys.readouterr().err


def test_exit_codes_are_the_documented_three():
    assert (cron_coverage.OK, cron_coverage.FAIL, cron_coverage.PROBE_ERROR) == (0, 1, 2)