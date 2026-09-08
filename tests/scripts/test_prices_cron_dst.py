"""DST correctness for the digithings-cron prices schedules (#1775 / #3579).

Every deadline the prices pipeline is trying to hit is an ``America/New_York``
wall-clock event — the 09:30 ET open and the 16:00 ET close — but GitHub cron is
fixed UTC and the ET offset moves by an hour twice a year. Before #1775 all three
jobs were wrong for roughly half the year, and in winter the intraday and EOD
errors overlapped such that *no* run of any job saw a settled regular-session
close: intraday stopped at 15:45 EST and eod-macro fired at 16:00 EST, at the bell.

So these tests deliberately assert on **derived ET local times**, not on the cron
strings. A snapshot of the literals would lock in whatever is currently written and
prove nothing about either season. Each schedule is expanded to UTC instants and
converted to ET on representative dates in both offsets, including the first
weekday after each 2026 transition, which is where this class of bug bites.

The Worker owns the clocks after #3579, while the workflow remains manually
dispatchable. These tests derive schedule literals from ``src/jobs.ts``, require
exact parity with ``wrangler.toml``, and continue exercising the workflow's ET
gate helper against an injected clock.
"""

from __future__ import annotations

import re
import subprocess
import sys
import tomllib
from datetime import date, datetime, time, timedelta, timezone
from pathlib import Path
from zoneinfo import ZoneInfo

import pytest
import yaml

pytestmark = pytest.mark.unit

REPO_ROOT = Path(__file__).resolve().parents[2]
WORKFLOW = REPO_ROOT / ".github" / "workflows" / "pipeline-digiquant-prices.yml"
JOBS_SOURCE = REPO_ROOT / "frontend" / "digithings-cron" / "src" / "jobs.ts"
WRANGLER = REPO_ROOT / "frontend" / "digithings-cron" / "wrangler.toml"

ET = ZoneInfo("America/New_York")
CASH_OPEN = time(9, 30)
CASH_CLOSE = time(16, 0)

# 2026 US DST: EDT from Mar 8 to Nov 1. Mid-season plus the first weekday after
# each transition — a schedule can be right in mid-January and wrong on Nov 2.
EST_DAYS = (date(2026, 1, 14), date(2026, 11, 2), date(2026, 12, 31))
EDT_DAYS = (date(2026, 3, 9), date(2026, 7, 15), date(2026, 10, 30))
ALL_DAYS = EST_DAYS + EDT_DAYS


@pytest.fixture(scope="module")
def workflow() -> dict:
    return yaml.safe_load(WORKFLOW.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def worker_jobs() -> dict[str, str]:
    """Read literal ``wd``/``rd`` job IDs and crons from the typed Worker map."""
    pairs = re.findall(
        r'(?:wd|rd)\(\s*"([^"]+)"\s*,\s*"([^"]+)"',
        JOBS_SOURCE.read_text(encoding="utf-8"),
        flags=re.DOTALL,
    )
    jobs = dict(pairs)
    assert pairs and len(jobs) == len(pairs), "Worker job IDs must be unique literal strings"
    return jobs


@pytest.fixture(scope="module")
def crons(worker_jobs: dict[str, str]) -> dict[str, list[str]]:
    """Price clocks grouped by the behavior the DST assertions exercise."""
    return {
        "intraday": [worker_jobs["prices-intraday"]],
        "fx-refresh": [
            worker_jobs["prices-fx-refresh"],
            worker_jobs["prices-fx-refresh-sun"],
        ],
        "eod-macro": [worker_jobs["prices-eod-macro"]],
        "at-open-clock": [
            worker_jobs["prices-at-open-13"],
            worker_jobs["prices-at-open-14"],
        ],
    }


def _expand_field(spec: str, lo: int, hi: int) -> list[int]:
    """Expand one numeric cron field: ``*``, ``a``, ``a-b``, ``*/n``, ``a-b/n``, lists.

    Anything else raises, so a future schedule written in a form this cannot read
    fails the suite instead of silently skipping the DST assertions.
    """
    values: set[int] = set()
    for part in spec.split(","):
        head, _, raw_step = part.partition("/")
        step = int(raw_step) if raw_step else 1
        if head == "*":
            start, end = lo, hi
        elif "-" in head:
            first, _, last = head.partition("-")
            start, end = int(first), int(last)
        else:
            start = end = int(head)
        if not (lo <= start <= end <= hi):
            raise ValueError(f"field {spec!r} out of range [{lo}, {hi}]")
        values.update(range(start, end + 1, step))
    return sorted(values)


def _utc_ticks(cron: str, day: date) -> list[datetime]:
    """Every UTC instant ``cron`` fires on ``day``."""
    minute, hour, dom, month, dow = cron.split()
    if (dom, month) != ("*", "*") or dow not in {"MON-FRI", "1-5"}:
        raise ValueError(f"unsupported day fields in {cron!r}")
    if day.weekday() > 4:
        return []
    return [
        datetime(day.year, day.month, day.day, h, m, tzinfo=timezone.utc)
        for h in _expand_field(hour, 0, 23)
        for m in _expand_field(minute, 0, 59)
    ]


def _et_ticks(cron: str, day: date) -> list[datetime]:
    """``cron``'s UTC instants, as ET wall clocks, for the ET-local ``day``.

    Ticks are anchored on the UTC date and every schedule here fires between 13:00
    and 22:00 UTC, so the ET date never differs from the UTC date; no re-anchoring
    is needed.
    """
    return [t.astimezone(ET) for t in _utc_ticks(cron, day)]


def _configured_crons() -> list[str]:
    parsed = tomllib.loads(WRANGLER.read_text(encoding="utf-8"))
    return parsed["triggers"]["crons"]


# --------------------------------------------------------------------------- #
# The schedules themselves, in both ET offsets
# --------------------------------------------------------------------------- #


def test_every_scheduled_job_is_still_named_as_expected(crons: dict[str, list[str]]) -> None:
    """The three job names the assertions below key on, and their cron counts."""
    assert {name: len(found) for name, found in crons.items()} == {
        "intraday": 1,
        "fx-refresh": 2,
        "eod-macro": 1,
        "at-open-clock": 2,
    }


@pytest.mark.parametrize("day", ALL_DAYS)
def test_intraday_covers_the_whole_et_session(crons: dict[str, list[str]], day: date) -> None:
    """Quotes must refresh from the open through the close in both offsets.

    The pre-#1775 ``*/15 13-20`` failed the close end under EST: its last tick was
    15:45, so the final quarter hour of every winter session — the one the live
    dashboard watches hardest — never refreshed.
    """
    ticks = [t.time() for cron in crons["intraday"] for t in _et_ticks(cron, day)]
    assert ticks, f"no intraday ticks on {day}"
    assert min(ticks) <= CASH_OPEN, f"{day}: first tick {min(ticks)} is after the 09:30 open"
    assert max(ticks) >= CASH_CLOSE, f"{day}: last tick {max(ticks)} is before the 16:00 close"


@pytest.mark.parametrize("day", ALL_DAYS)
def test_eod_runs_after_a_settled_close(crons: dict[str, list[str]], day: date) -> None:
    """EOD is the only job that fetches the sector single names (`--include-sectors`).

    Pre-#1775 ``0 21`` was 16:00 EST — fired *at* the bell, so every winter sector
    read got an unsettled intra-session bar rather than the close. Require a real
    settle buffer, not merely "after 16:00".
    """
    ticks = [t for cron in crons["eod-macro"] for t in _et_ticks(cron, day)]
    assert len(ticks) == 1, f"{day}: expected one EOD tick, got {len(ticks)}"
    settled = datetime.combine(day, CASH_CLOSE, tzinfo=ET) + timedelta(minutes=20)
    assert ticks[0] >= settled, f"{day}: EOD at {ticks[0]:%H:%M %Z} is too close to the bell"


@pytest.mark.parametrize("day", ALL_DAYS)
def test_eod_finishes_before_the_metrics_cron_and_shares_no_minute_with_intraday(
    crons: dict[str, list[str]],
    day: date,
) -> None:
    """Two constraints that pin the EOD *minute* rather than its hour.

    ``pipeline-research-metrics.yml``'s ``0 22`` cron documents that it must run after
    this ingest, and the job's own ``timeout-minutes`` bounds the worst case. And
    since intraday now extends through hour 21, an EOD minute on the 15-minute grid
    would collide with an intraday tick — ``digiquant-prices-intraday`` is a per-job
    concurrency group and does not cover eod-macro, so that would be two concurrent
    yfinance pulls over the same tickers.
    """
    (eod,) = [t for cron in crons["eod-macro"] for t in _utc_ticks(cron, day)]
    intraday = {t for cron in crons["intraday"] for t in _utc_ticks(cron, day)}
    metrics_cron = datetime(day.year, day.month, day.day, 22, 0, tzinfo=timezone.utc)
    assert eod + timedelta(minutes=20) <= metrics_cron, "EOD can overrun the metrics cron"
    assert eod not in intraday, "EOD shares a minute with an intraday tick"


@pytest.mark.parametrize("day", ALL_DAYS)
def test_exactly_one_at_open_cron_lands_just_after_the_open(
    crons: dict[str, list[str]],
    day: date,
) -> None:
    """No single UTC cron can satisfy at-open, hence two crons plus the ET gate.

    The offsets differ by exactly one hour, so a fixed minute is either ~65 min late
    in one season (the pre-#1775 ``35 14``, which was 10:35 EDT) or ~55 min early in
    the other. Requiring exactly one admitted cron is what makes the pair safe: a
    second admitted run would be the pre-open one, and pre-open is unrepairable.
    """
    open_et = datetime.combine(day, CASH_OPEN, tzinfo=ET)
    admitted = [
        tick
        for cron in crons["at-open-clock"]
        for tick in _et_ticks(cron, day)
        if open_et <= tick <= open_et + timedelta(minutes=30)
    ]
    assert len(admitted) == 1, f"{day}: {len(admitted)} at-open crons in [09:30, 10:00] ET"
    assert admitted[0] - open_et <= timedelta(minutes=10), f"{day}: at-open is late"


# --------------------------------------------------------------------------- #
# Worker job map <-> deployed trigger linkage
# --------------------------------------------------------------------------- #


def test_worker_jobs_and_wrangler_triggers_have_exact_cron_parity(
    worker_jobs: dict[str, str],
) -> None:
    configured = _configured_crons()
    assert len(configured) == len(set(configured)), "wrangler has duplicate cron triggers"
    assert set(worker_jobs.values()) == set(configured)


# --------------------------------------------------------------------------- #
# The ET gate helper
# --------------------------------------------------------------------------- #


def _gate_path(workflow: dict) -> Path:
    steps = workflow["jobs"]["at-open-clock"]["steps"]
    run = next(step["run"] for step in steps if step.get("id") == "clock")
    match = re.search(r"python3\s+(\S*market_open_gate\.py)", run)
    assert match, "the at-open workflow no longer invokes the tested gate helper"
    return REPO_ROOT / match.group(1)


def _run_gate(path: Path, now: str | None, schedule: str = "", force: bool = False) -> str:
    """Execute the workflow's gate helper against an injected clock.

    In the job, bash appends the script's stdout to ``$GITHUB_OUTPUT``, so stdout is
    exactly what GitHub parses — hence asserting on it here rather than on a file.
    """
    args = [sys.executable, str(path), "--schedule", schedule]
    if now is not None:
        args.extend(["--now-utc", now])
    if force:
        args.append("--force")
    done = subprocess.run(
        args,
        capture_output=True,
        text=True,
        check=True,
        timeout=60,
    )
    written = done.stdout.splitlines()
    assert len(written) == 1, f"gate wrote {written!r} to GITHUB_OUTPUT; expected one key"
    key, _, value = written[0].partition("=")
    assert key == "in_window"
    return value


@pytest.mark.parametrize(
    ("now_utc", "schedule", "expected", "why"),
    [
        ("2026-07-15T13:35", "35 13 * * MON-FRI", "true", "EDT: correct summer cron"),
        ("2026-07-15T14:35", "35 14 * * MON-FRI", "false", "EDT: winter cron"),
        ("2026-01-14T14:35", "35 14 * * MON-FRI", "true", "EST: correct winter cron"),
        ("2026-01-14T13:35", "35 13 * * MON-FRI", "false", "EST: pre-open"),
        ("2026-03-09T13:35", "35 13 * * MON-FRI", "true", "spring transition"),
        ("2026-03-09T14:35", "35 14 * * MON-FRI", "false", "spring wrong cron"),
        ("2026-11-02T14:35", "35 14 * * MON-FRI", "true", "autumn transition"),
        ("2026-11-02T13:35", "35 13 * * MON-FRI", "false", "autumn wrong cron"),
        ("2026-07-15T13:55", "35 13 * * MON-FRI", "true", "20-minute delay"),
        ("2026-07-15T15:41", "35 13 * * MON-FRI", "true", "two-hour delay"),
        ("2026-07-15T20:00", "35 13 * * MON-FRI", "true", "hours-late delivery"),
        ("2026-07-15T13:29", "35 13 * * MON-FRI", "false", "pre-open"),
    ],
)
def test_gate_admits_only_the_in_season_cron(
    workflow: dict, now_utc: str, schedule: str, expected: str, why: str
) -> None:
    assert _run_gate(_gate_path(workflow), now_utc, schedule) == expected, why


def test_gate_never_blocks_a_manual_dispatch(workflow: dict) -> None:
    """`workflow_dispatch` is an operator override; gating it would be a foot-gun."""
    path = _gate_path(workflow)
    assert _run_gate(path, "2026-07-15T19:00") == "false"
    assert _run_gate(path, "2026-07-15T19:00", force=True) == "true"


def test_gate_falls_back_to_the_wall_clock(workflow: dict) -> None:
    """With no override the gate must read the real clock, not fail or default open."""
    assert _run_gate(_gate_path(workflow), None) in {"true", "false"}


def test_at_open_cannot_run_without_the_gate(workflow: dict) -> None:
    """The gate lives in its own job so a step added to at-open cannot escape it."""
    clock = workflow["jobs"]["at-open-clock"]
    at_open = workflow["jobs"]["at-open"]
    assert at_open["needs"] == "at-open-clock"
    assert "needs.at-open-clock.outputs.in_window == 'true'" in at_open["if"]
    assert clock["outputs"]["in_window"] == "${{ steps.clock.outputs.in_window }}"
    assert clock["permissions"] == {"contents": "read"}
    clock_checkout = next(step for step in clock["steps"] if "checkout" in step.get("uses", ""))
    assert "ref" not in clock_checkout.get("with", {})
    writer_checkout = next(step for step in at_open["steps"] if "checkout" in step.get("uses", ""))
    assert writer_checkout["with"]["ref"] == "main"
    run = next(step["run"] for step in clock["steps"] if step.get("id") == "clock")
    assert '>> "$GITHUB_OUTPUT"' in run, "the gate's decision never reaches the job output"


# --------------------------------------------------------------------------- #
# What the at-open job actually invokes (#2420, Task 2.4)
# --------------------------------------------------------------------------- #


def _at_open_command(workflow: dict) -> str:
    """The shell line that runs the at-open writer, wherever in the job it sits.

    Found by the script's own name rather than by step index or step name, so reordering
    the job or renaming the step keeps the flag assertions below pointed at the right line.

    Narrowed to the invoking line with shell comments stripped, so the flag assertions read
    the command and nothing else. Today the prose above this step is a YAML comment, which
    the parser drops before `step["run"]` ever exists — but a `run: |` block that grew a
    second line and an inline `# ... --require-ledger ...` note would otherwise turn a
    comment into a passing or failing assertion about behaviour.
    """
    steps = workflow["jobs"]["at-open"]["steps"]
    runs = [str(step["run"]) for step in steps if "execute_at_open.py" in str(step.get("run", ""))]
    assert len(runs) == 1, f"expected exactly one at-open invocation, found {len(runs)}"
    lines = [
        line.split("#", 1)[0].strip()
        for line in runs[0].splitlines()
        if "execute_at_open.py" in line.split("#", 1)[0]
    ]
    assert len(lines) == 1, f"expected one at-open command line, found {len(lines)}: {lines}"
    return lines[0]


def test_at_open_fills_the_prior_days_rebalance(workflow: dict) -> None:
    """The decision is made after one close and filled at the next open.

    Without ``--prior-trading-day-rebalance`` the script looks for a rebalance dated today,
    finds none at 09:35, and books nothing — a silent no-op, not an error. The flag is the
    only thing that points it at yesterday's approved targets.
    """
    assert "--prior-trading-day-rebalance" in _at_open_command(workflow)


def test_at_open_requires_the_ledger_after_opening_snapshot_cutover(workflow: dict) -> None:
    """After #2589 the cron trusts the ledger path with an explicit require flag.

    ``ensure_legacy_opening_snapshot`` seeds (or cold-start-declines) before fills, so
    ``--no-ledger`` is gone and ``--require-ledger`` is pinned *present*: a decline becomes
    exit 3 instead of a silent prose fallback that could hide a failed handover.
    """
    command = _at_open_command(workflow)
    assert "--no-ledger" not in command
    assert "--require-ledger" in command
