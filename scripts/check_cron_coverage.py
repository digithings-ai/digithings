#!/usr/bin/env python3
"""Cron-coverage check: did every scheduled workflow actually run? (#217)

Why this exists
---------------
The ``digithings-cron`` Cloudflare Worker is the production clock. In
``apps/digithings-cron/src/index.ts`` each dispatch is handed to
``ctx.waitUntil(Promise.all(pending))`` and the fetch handler returns
immediately, so **a dispatch that never reaches GitHub is invisible to the
Worker's own invocation**: the cron tick reports success and no GitHub run is
created at all.

That is an *absence*, not a failure, and every existing detector only looks at
runs that exist:

* ``pipeline-maintenance.yml`` -> ``workflow-health`` queries
  ``actions/runs?status=failure`` — it can only see runs that were created
  *and* failed. Zero runs is zero rows, which reads as "nothing to report".
* ``token-canary.yml`` (#3522) proves a credential still authenticates. It
  cannot tell you *which* jobs stopped when a dispatch is refused upstream.

On 2026-09-28T15:52Z -> 2026-10-01T23:52Z the hourly twelve-x session
catch-up produced no runs at all for ~3.3 days and nothing alerted. This script
is the detector for that signature.

How it decides
--------------
Expected work is derived from ``apps/digithings-cron/src/jobs.ts`` — the same
declarative job list the Worker dispatches from, so the expectation cannot
drift from the thing being checked. Each enabled job's cron is expanded over a
trailing window to get an **expected** run count; GitHub's Actions API supplies
the **observed** count for the same workflow and dispatch event. Then:

* ``expected == 0``            -> ``skipped`` (not due in this window)
* ``expected > 0, seen == 0``  -> ``missing``  — DIG-217's exact signature
* ``0 < seen < expected - tol``-> ``degraded`` — partially delivered
* otherwise                    -> ``ok``

``etOpenGate`` jobs (market-at-open price pulls) are reported but **never
failed**: a market holiday is indistinguishable from a dropped dispatch without
a trading calendar, and failing on holidays every Christmas would train everyone
to ignore this check. They are reported as ``gated`` so the gap is visible
without being a false alarm.

The tolerance applies only to ``degraded``. ``missing`` is never tolerated: a
daily job observed zero times in a 48h window is a real signal, and letting a
tolerance of 1 cover it would defeat the entire purpose of the check.

Exit codes
----------
``0`` — no job is missing or degraded. ``1`` — at least one is; this is the
state that should file a tracker. ``2`` — the check could not run (jobs.ts not
found, ``gh`` unavailable, API unreachable), reported but never confused with a
coverage failure. ``--plan-only`` prints the expected counts and exits 0
without touching the network.

Usage
-----
::

    python3 scripts/check_cron_coverage.py --plan-only
    python3 scripts/check_cron_coverage.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import re
import subprocess
import sys
from dataclasses import asdict, dataclass, field
from datetime import datetime, timedelta, timezone
from pathlib import Path
from typing import Dict, Iterable, List, Optional, Sequence, Tuple

OK = 0
FAIL = 1
PROBE_ERROR = 2

REPO_ROOT = Path(__file__).resolve().parents[1]
JOBS_TS = REPO_ROOT / "apps" / "digithings-cron" / "src" / "jobs.ts"

DEFAULT_WINDOW_HOURS = 48
DEFAULT_TOLERANCE = 1
API_PAGE_SIZE = 100
MAX_PAGES = 5

WEEKDAYS = {
    "SUN": 0,
    "MON": 1,
    "TUN": 2,
    "WED": 3,
    "THU": 4,
    "FRI": 5,
    "SAT": 6,
}
MONTHS = {
    "JAN": 1,
    "FEB": 2,
    "MAR": 3,
    "APR": 4,
    "MAY": 5,
    "JUN": 6,
    "JUL": 7,
    "AUG": 8,
    "SEP": 9,
    "OCT": 10,
    "NOV": 11,
    "DEC": 12,
}


# --------------------------------------------------------------------------
# cron parsing / expansion
# --------------------------------------------------------------------------


class CronError(ValueError):
    """Raised when a cron expression cannot be understood."""


def parse_iso_utc(raw: str) -> datetime:
    """Parse an ISO-8601 timestamp into an aware UTC datetime.

    A trailing ``Z`` is accepted and normalized by hand rather than relying on
    ``datetime.fromisoformat``, which only learned to read it in Python 3.11.
    GitHub's API and ``date -u`` both emit ``Z``, so this is the common case and
    it has to work on whichever interpreter runs the check.
    """
    text = raw.strip()
    if text.endswith(("Z", "z")):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


@dataclass(frozen=True)
class Field:
    values: frozenset
    star: bool


def _parse_field(raw: str, names: Dict[str, int], low: int, high: int, label: str) -> Field:
    """Expand one cron field into the set of values it matches.

    Supports ``*``, ``*/step``, ``a``, ``a-b``, ``a-b/step`` and comma lists,
    plus the three-letter names Cloudflare cron uses for weekdays and months.
    Numeric day-of-week is deliberately accepted as well — ``jobs.test.ts``
    forbids it for the *Worker's* crons because Cloudflare reinterprets it, but
    this script only has to read whatever is already committed.
    """
    raw = raw.strip()
    if not raw:
        raise CronError(f"empty {label} field")

    is_star = raw == "*"
    values: set = set()

    for part in raw.split(","):
        part = part.strip()
        if not part:
            raise CronError(f"empty {label} element in {raw!r}")

        step = 1
        if "/" in part:
            part, _, step_raw = part.partition("/")
            part = part.strip()
            try:
                step = int(step_raw)
            except ValueError as exc:
                raise CronError(f"bad step {step_raw!r} in {label} field {raw!r}") from exc
            if step <= 0:
                raise CronError(f"step must be positive in {label} field {raw!r}")

        if part == "*":
            start, end = low, high
        elif "-" in part[1:]:
            idx = part.index("-", 1)
            start = _parse_value(part[:idx], names, label, raw)
            end = _parse_value(part[idx + 1 :], names, label, raw)
        else:
            start = _parse_value(part, names, label, raw)
            end = high if step > 1 else start

        if start > end:
            raise CronError(f"reversed range in {label} field {raw!r}")

        values.update(range(start, end + 1, step))

    values = {v for v in values if low <= v <= high}
    if not values:
        raise CronError(f"{label} field {raw!r} matches nothing")
    return Field(values=frozenset(values), star=is_star)


def _parse_value(token: str, names: Dict[str, int], label: str, raw: str) -> int:
    token = token.strip()
    if not token:
        raise CronError(f"empty value in {label} field {raw!r}")
    upper = token.upper()
    if upper in names:
        return names[upper]
    try:
        return int(token)
    except ValueError as exc:
        raise CronError(f"unrecognised value {token!r} in {label} field {raw!r}") from exc


@dataclass(frozen=True)
class CronSpec:
    minute: Field
    hour: Field
    dom: Field
    month: Field
    dow: Field
    raw: str

    def matches(self, moment: datetime) -> bool:
        # Vixie semantics: when both day-of-month and day-of-week are restricted
        # the day matches if *either* does. Every cron in jobs.ts leaves dom as
        # "*", so this never fires today, but it is implemented rather than
        # assumed.
        dom_ok = moment.day in self.dom.values
        dow_ok = ((moment.weekday() + 1) % 7) in self.dow.values
        if not self.dom.star and not self.dow.star:
            day_ok = dom_ok or dow_ok
        else:
            day_ok = dom_ok and dow_ok
        return (
            moment.minute in self.minute.values
            and moment.hour in self.hour.values
            and moment.month in self.month.values
            and day_ok
        )


def parse_cron(expr: str) -> CronSpec:
    parts = expr.split()
    if len(parts) != 5:
        raise CronError(f"cron {expr!r} must have 5 fields, got {len(parts)}")
    minute, hour, dom, month, dow = parts
    return CronSpec(
        minute=_parse_field(minute, {}, 0, 59, "minute"),
        hour=_parse_field(hour, {}, 0, 23, "hour"),
        dom=_parse_field(dom, {}, 1, 31, "day-of-month"),
        month=_parse_field(month, MONTHS, 1, 12, "month"),
        dow=_parse_field(dow, WEEKDAYS, 0, 6, "day-of-week"),
        raw=expr,
    )


def expected_runs(expr: str, start: datetime, end: datetime) -> int:
    """Count how many times ``expr`` fires in the half-open window [start, end)."""
    spec = parse_cron(expr)
    if end <= start:
        return 0
    # Step the cursor to the top of the next minute so a window boundary never
    # double-counts or skips a tick.
    cursor = start.replace(second=0, microsecond=0)
    if cursor < start:
        cursor += timedelta(minutes=1)

    count = 0
    while cursor < end:
        if spec.matches(cursor):
            count += 1
        cursor += timedelta(minutes=1)
    return count


# --------------------------------------------------------------------------
# jobs.ts parsing — the expectation is read from the Worker's own source
# --------------------------------------------------------------------------


@dataclass(frozen=True)
class ExpectedJob:
    id: str
    cron: str
    repo: str
    kind: str
    workflow: Optional[str]
    et_open_gate: bool

    @property
    def target(self) -> str:
        return self.workflow if self.kind == "workflow_dispatch" else self.kind


def _balanced_slice(source: str, open_idx: int, opener: str = "(", closer: str = ")") -> str:
    """Return the text from ``open_idx`` to its matching closer.

    Tracks quotes, escapes and every bracket kind so a ``)`` inside a string
    literal cannot end the scan early.
    """
    depth = 0
    quote: Optional[str] = None
    escaped = False
    stack: List[str] = []

    for i in range(open_idx, len(source)):
        ch = source[i]
        if quote is not None:
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'`":
            quote = ch
            continue
        if ch in "([{":
            stack.append(ch)
        elif ch in ")]}":
            if not stack:
                break
            stack.pop()
            if not stack and ch == closer:
                return source[open_idx : i + 1]
    raise ValueError(f"unbalanced {opener!r} starting at offset {open_idx}")


def _split_top_level(text: str) -> List[str]:
    """Split on commas that sit outside any bracket or string literal."""
    parts: List[str] = []
    depth = 0
    quote: Optional[str] = None
    escaped = False
    current: List[str] = []
    for ch in text:
        if quote is not None:
            current.append(ch)
            if escaped:
                escaped = False
            elif ch == "\\":
                escaped = True
            elif ch == quote:
                quote = None
            continue
        if ch in "\"'`":
            quote = ch
            current.append(ch)
            continue
        if ch in "([{":
            depth += 1
        elif ch in ")]}":
            depth -= 1
        if ch == "," and depth == 0:
            parts.append("".join(current).strip())
            current = []
            continue
        current.append(ch)
    parts.append("".join(current).strip())
    return parts


def _unquote(token: str) -> str:
    token = token.strip()
    if len(token) >= 2 and token[0] == token[-1] and token[0] in "\"'`":
        return token[1:-1]
    raise ValueError(f"expected a quoted string, got {token!r}")


def _repo_constants(source: str) -> Dict[str, str]:
    out: Dict[str, str] = {}
    for name, value in re.findall(r'const\s+([A-Z][A-Z0-9_]*)\s*=\s*"([^"]+)"', source):
        out[name] = value
    return out


def parse_jobs_ts(path: Path) -> List[ExpectedJob]:
    """Read the enabled job list out of ``jobs.ts``.

    Only the two constructor calls the Worker uses are recognised (``wd`` for
    ``workflow_dispatch``, ``rd`` for ``repository_dispatch``). Unknown call
    shapes raise rather than being skipped, so a refactor that hides a job
    fails the check instead of silently shrinking the expectation.
    """
    source = path.read_text(encoding="utf-8")
    repos = _repo_constants(source)
    jobs: List[ExpectedJob] = []
    seen: Dict[str, str] = {}

    # The leading `(` must be followed by a quoted string: that is a real call
    # site. The `function wd(id: string, ...)` declaration has `id: string`
    # there and is correctly skipped.
    for match in re.finditer(r'\b(wd|rd)\s*\(\s*"', source):
        kind_fn = match.group(1)
        call = _balanced_slice(source, source.index("(", match.start()))
        # Drop the leading "(" and the trailing ")".
        args = _split_top_level(call[1:-1])
        if len(args) < 4:
            raise ValueError(f"cannot read positional args from {kind_fn}(...) near: {call[:120]}")

        job_id = _unquote(args[0])
        cron = _unquote(args[1])
        # The third positional is a bare const (DIGITHINGS / TWELVE_X), not a
        # literal, which is why the args are read positionally and not by regex.
        repo_ref = args[2].strip()
        third = _unquote(args[3])
        opts = args[4] if len(args) > 4 else ""

        if repo_ref not in repos:
            raise ValueError(f"job {job_id!r} uses unknown repo constant {repo_ref!r}")

        if kind_fn == "wd":
            kind = "workflow_dispatch"
            workflow: Optional[str] = third
        else:
            kind = "repository_dispatch"
            workflow = None

        if re.search(r"\benabled\s*:\s*false\b", opts):
            continue  # disabled job: the Worker will never dispatch it

        if job_id in seen:
            raise ValueError(f"duplicate job id {job_id!r} in {path}")
        seen[job_id] = cron

        jobs.append(
            ExpectedJob(
                id=job_id,
                cron=cron,
                repo=repos[repo_ref],
                kind=kind,
                # For `rd` the 4th positional is the event_type
                # ("digiquant-baseline"), not a workflow path. The runs API
                # filters on `event=repository_dispatch` instead, which is what
                # `ExpectedJob.target` reports for that kind.
                workflow=workflow,
                et_open_gate=bool(re.search(r"\betOpenGate\s*:\s*true\b", opts)),
            )
        )

    if not jobs:
        raise ValueError(f"no enabled jobs found in {path}")
    return jobs


# --------------------------------------------------------------------------
# observation — the observed side, from GitHub
# --------------------------------------------------------------------------


@dataclass
class Observed:
    seen: int = 0
    error: Optional[str] = None
    newest_run: Optional[str] = None


class GitHubReader:
    """Reads workflow runs via the ``gh`` CLI.

    ``gh`` is used (rather than raw fetch) so the token comes from the same
    ``GH_TOKEN`` env the other maintenance workflows already use, and so the
    script needs no HTTP dependency.
    """

    def __init__(self, token: Optional[str], api: str = "https://api.github.com") -> None:
        self.token = token
        self.api = api.rstrip("/")
        self.calls = 0

    def _env(self) -> Dict[str, str]:
        env = dict(os.environ)
        if self.token:
            env["GH_TOKEN"] = self.token
        return env

    def run_counts(self, repo: str, workflow: str, event: str, since: datetime) -> Observed:
        result = Observed()
        created = since.astimezone(timezone.utc).strftime("%Y-%m-%dT%H:%M:%SZ")
        page = 1
        while page <= MAX_PAGES:
            path = (
                f"{self.api}/repos/{repo}/actions/workflows/{workflow}/runs"
                f"?event={event}&created=%3E%3D{created}&per_page={API_PAGE_SIZE}&page={page}"
            )
            cmd = ["gh", "api", "-H", "Accept: application/vnd.github+json", path]
            proc = subprocess.run(cmd, capture_output=True, text=True, env=self._env())
            self.calls += 1
            if proc.returncode != 0:
                detail = (proc.stderr or proc.stdout).strip().splitlines()
                result.error = detail[-1] if detail else f"gh exited {proc.returncode}"
                return result
            try:
                payload = json.loads(proc.stdout or "{}")
            except json.JSONDecodeError as exc:
                result.error = f"unparseable API response: {exc}"
                return result

            runs = payload.get("workflow_runs") or []
            for run in runs:
                result.seen += 1
                created_at = run.get("created_at")
                if created_at and (result.newest_run is None or created_at > result.newest_run):
                    result.newest_run = created_at

            if len(runs) < API_PAGE_SIZE:
                return result
            page += 1

        result.error = f"more than {MAX_PAGES * API_PAGE_SIZE} runs in window; count is a floor"
        return result


# --------------------------------------------------------------------------
# evaluation — pure, so the verdict logic is testable without a network
# --------------------------------------------------------------------------

STATUS_OK = "ok"
STATUS_MISSING = "missing"
STATUS_DEGRADED = "degraded"
STATUS_SKIPPED = "skipped"
STATUS_GATED = "gated"
STATUS_PROBE_ERROR = "probe-error"

FAILING_STATUSES = {STATUS_MISSING, STATUS_DEGRADED}


@dataclass
class Row:
    job: ExpectedJob
    status: str
    expected: int
    observed: int
    tolerance: int
    note: str = ""
    newest_run: Optional[str] = None
    group_expected: int = 0
    group_size: int = 1

    @property
    def fails(self) -> bool:
        return self.status in FAILING_STATUSES

    @property
    def shared(self) -> bool:
        return self.group_size > 1

    @property
    def compared_against(self) -> int:
        """The expected count this row's verdict was actually measured against."""
        return self.group_expected if self.shared else self.expected

    def to_dict(self) -> dict:
        data = asdict(self.job)
        data.update(
            {
                "status": self.status,
                "expected": self.expected,
                "observed": self.observed,
                "tolerance": self.tolerance,
                "fails": self.fails,
                "note": self.note,
                "newest_run": self.newest_run,
                "group_expected": self.group_expected,
                "group_size": self.group_size,
                "compared_against": self.compared_against,
            }
        )
        return data


def classify(
    job: ExpectedJob,
    expected: int,
    observed: Observed,
    tolerance: int,
    group_expected: Optional[int] = None,
    group_size: int = 1,
) -> Row:
    """Decide one row's status. Pure: no clock and no network.

    ``group_expected`` is the summed expectation of every clock that dispatches
    the same workflow. GitHub records *that* a run happened but never *which cron*
    created it, so a shared target can only be measured as a group — see
    ``build_rows`` for why per-clock counting there would be unsound.
    """
    if group_expected is None:
        group_expected = expected

    if observed.error:
        return Row(job, STATUS_PROBE_ERROR, expected, observed.seen, tolerance,
                   note=observed.error, group_expected=group_expected,
                   group_size=group_size)

    if group_expected == 0:
        return Row(job, STATUS_SKIPPED, 0, observed.seen, tolerance,
                   note="not due inside the window", group_expected=0,
                   group_size=group_size)

    # DIG-217: work was due, zero runs. Never tolerated.
    if observed.seen == 0:
        row = Row(job, STATUS_MISSING, expected, 0, tolerance,
                  note="the clock should have dispatched this and no run exists",
                  group_expected=group_expected, group_size=group_size)
        if job.et_open_gate:
            row.status = STATUS_GATED
            row.note += " (market-gated job: a holiday looks identical to a dropped run)"
        return row

    if observed.seen < group_expected - tolerance:
        row = Row(job, STATUS_DEGRADED, expected, observed.seen, tolerance,
                  group_expected=group_expected, group_size=group_size)
        short = group_expected - observed.seen
        if group_size > 1:
            row.note = (
                f"{short} of {group_expected} run(s) absent across the "
                f"{group_size} clocks sharing this workflow, beyond tolerance"
            )
        else:
            row.note = f"{short} expected run(s) absent beyond tolerance"
        return row

    return Row(job, STATUS_OK, expected, observed.seen, tolerance,
               newest_run=observed.newest_run, group_expected=group_expected,
               group_size=group_size)


def _target_key(job: ExpectedJob) -> Tuple[str, str, str]:
    return (job.repo, job.kind, job.target or "")


def build_rows(
    jobs: Sequence[ExpectedJob],
    observed: Dict[Tuple[str, str, str], Observed],
    start: datetime,
    end: datetime,
    tolerance: int,
) -> List[Row]:
    """One row per clock, each measured against its shared-workflow group.

    Several clocks legitimately dispatch the same workflow — six of them reach
    ``pipeline-digiquant-prices.yml`` in digithings alone. The runs API can only
    answer "how many runs does this workflow have in the window", never "which
    cron started each one". Counting per clock against that shared total would
    let one dead clock hide inside its siblings' runs: prices-intraday dies, the
    other five keep the workflow's total above every clock's expectation, and
    the check reports ok. So the verdict is taken on the group's summed
    expectation and repeated onto each member, while each row keeps its own
    ``expected`` for the reader.
    """
    expected_by_job = {j.id: expected_runs(j.cron, start, end) for j in jobs}

    members: Dict[Tuple[str, str, str], List[ExpectedJob]] = {}
    for job in jobs:
        members.setdefault(_target_key(job), []).append(job)
    group_expected = {
        key: sum(expected_by_job[m.id] for m in group) for key, group in members.items()
    }

    rows: List[Row] = []
    for job in jobs:
        key = _target_key(job)
        rows.append(
            classify(
                job,
                expected_by_job[job.id],
                observed.get(key, Observed(error="not queried")),
                tolerance,
                group_expected=group_expected[key],
                group_size=len(members[key]),
            )
        )
    return rows


# --------------------------------------------------------------------------
# reporting
# --------------------------------------------------------------------------


def _expected_cell(row: Row) -> str:
    """Expected count, qualified when the verdict was taken on a shared group."""
    if row.shared:
        return f"{row.expected} of {row.compared_against}"
    return str(row.expected)


def render_markdown(rows: Sequence[Row], start: datetime, end: datetime, api_calls: int) -> str:
    failing = [r for r in rows if r.fails]
    gated = [r for r in rows if r.status == STATUS_GATED]
    probed = [r for r in rows if r.status != STATUS_PROBE_ERROR]
    errs = [r for r in rows if r.status == STATUS_PROBE_ERROR]

    lines = [
        "## Cron coverage — expected vs observed",
        "",
        f"Window: `{start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`"
        f" → `{end.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%M:%SZ')}`",
        "",
        f"- jobs checked: **{len(rows)}** ({len(probed)} probed, {len(failing)} failing, "
        f"{len(gated)} market-gated, {len(errs)} not probed)",
        f"- GitHub API calls: **{api_calls}**",
        "",
    ]

    if failing:
        lines += [
            "### Failing — the clock dispatched nothing the workflow recorded",
            "",
            "| job | cron | repo | workflow | expected | observed | note |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in failing:
            lines.append(
                f"| `{r.job.id}` | `{r.job.cron}` | `{r.job.repo}` | `{r.job.target}` "
                f"| {_expected_cell(r)} | **{r.observed}** | {r.note} |"
            )
        lines.append("")

    if gated:
        lines += [
            "### Market-gated — reported, never failed",
            "",
            "A holiday and a dropped dispatch look identical without a trading",
            "calendar, so these cannot fail the check.",
            "",
            "| job | cron | repo | workflow | expected | observed | newest run |",
            "| --- | --- | --- | --- | --- | --- | --- |",
        ]
        for r in gated:
            lines.append(
                f"| `{r.job.id}` | `{r.job.cron}` | `{r.job.repo}` | `{r.job.target}` "
                f"| {r.expected} | {r.observed} | {r.newest_run or '—'} |"
            )
        lines.append("")

    if errs:
        lines += [
            "### Not probed — the check could not read this job",
            "",
            "These are **not** coverage failures. The read failed; the state is unknown.",
            "",
            "| job | repo | workflow | error |",
            "| --- | --- | --- | --- |",
        ]
        for r in errs:
            lines.append(f"| `{r.job.id}` | `{r.job.repo}` | `{r.job.target}` | {r.note} |")
        lines.append("")

    lines += [
        "<details><summary>All jobs</summary>",
        "",
        "`expected` is this clock's own tick count. `observed` is the run count of",
        "the whole target, so a clock that shares its workflow with others is judged",
        "on the group's total (shown as `own of group`).",
        "",
        "| job | cron | repo | target | expected | observed | status |",
        "| --- | --- | --- | --- | --- | --- | --- |",
    ]
    for r in rows:
        lines.append(
            f"| `{r.job.id}` | `{r.job.cron}` | `{r.job.repo}` | `{r.job.target}` "
            f"| {_expected_cell(r)} | {r.observed} | {r.status} |"
        )
    lines += ["", "</details>", ""]
    return "\n".join(lines)


def render_text(rows: Sequence[Row], start: datetime, end: datetime) -> str:
    lines = [
        f"cron coverage {start.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}"
        f" -> {end.astimezone(timezone.utc).strftime('%Y-%m-%dT%H:%MZ')}",
        "",
    ]
    width = max(len(r.job.id) for r in rows) if rows else 10
    for r in rows:
        lines.append(
            f"{r.status:<12} {r.job.id:<{width}}  {r.job.cron:<16}"
            f" expected={_expected_cell(r):<9} observed={r.observed:<4} {r.note}"
        )
    failing = [r for r in rows if r.fails]
    lines += ["", f"{len(failing)} failing of {len(rows)} jobs"]
    return "\n".join(lines)


# --------------------------------------------------------------------------
# entry point
# --------------------------------------------------------------------------


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    p.add_argument("--jobs-ts", type=Path, default=JOBS_TS, help="path to jobs.ts")
    p.add_argument(
        "--window-hours",
        type=float,
        default=DEFAULT_WINDOW_HOURS,
        help=(
            "trailing window to compare. Default 48h: a daily job has at least "
            "one due tick inside it, so 'no runs at all' is unambiguous, and two "
            "days of slack absorbs a single late tick."
        ),
    )
    p.add_argument(
        "--tolerance",
        type=int,
        default=DEFAULT_TOLERANCE,
        help=(
            "runs that may be absent before a partially-delivered job is called "
            "degraded. Never applied to a job with zero runs."
        ),
    )
    p.add_argument("--now", help="ISO-8601 override for the window end (tests)")
    p.add_argument("--token", default=os.environ.get("DIGITHINGS_PROJECT_TOKEN"))
    p.add_argument("--api", default="https://api.github.com")
    p.add_argument("--json", action="store_true", dest="as_json", help="machine-readable verdict")
    p.add_argument(
        "--plan-only",
        action="store_true",
        help="print expected counts from jobs.ts and exit without calling GitHub",
    )
    return p


def main(argv: Optional[Sequence[str]] = None) -> int:
    args = build_parser().parse_args(argv)

    try:
        jobs = parse_jobs_ts(args.jobs_ts)
    except (OSError, ValueError, CronError) as exc:
        print(f"cannot read the job clock from {args.jobs_ts}: {exc}", file=sys.stderr)
        return PROBE_ERROR

    if args.now:
        try:
            end = parse_iso_utc(args.now)
        except ValueError as exc:
            print(f"--now is not a valid ISO-8601 timestamp: {exc}", file=sys.stderr)
            return PROBE_ERROR
    else:
        end = datetime.now(timezone.utc)
    start = end - timedelta(hours=args.window_hours)

    try:
        for job in jobs:
            expected_runs(job.cron, start, end)  # fail fast on an unparseable cron
    except CronError as exc:
        print(f"cannot expand a cron expression: {exc}", file=sys.stderr)
        return PROBE_ERROR

    if args.plan_only:
        if args.as_json:
            print(
                json.dumps(
                    {
                        "window_start": start.isoformat(),
                        "window_end": end.isoformat(),
                        "jobs": [
                            {
                                "id": j.id,
                                "cron": j.cron,
                                "repo": j.repo,
                                "kind": j.kind,
                                "target": j.target,
                                "etOpenGate": j.et_open_gate,
                                "expected": expected_runs(j.cron, start, end),
                            }
                            for j in jobs
                        ],
                    },
                    indent=2,
                )
            )
        else:
            print(render_text(build_rows(jobs, {}, start, end, args.tolerance), start, end))
        return OK

    targets = {(j.repo, j.kind, j.target or "") for j in jobs}
    reader = GitHubReader(args.token, args.api)

    probe_errors: List[str] = []
    observed: Dict[Tuple[str, str, str], Observed] = {}
    for repo, kind, target in sorted(targets):
        result = reader.run_counts(repo, target, kind, start)
        observed[(repo, kind, target)] = result
        if result.error:
            probe_errors.append(f"{repo}/{target}: {result.error}")

    rows = build_rows(jobs, observed, start, end, args.tolerance)

    if args.as_json:
        print(
            json.dumps(
                {
                    "window_start": start.isoformat(),
                    "window_end": end.isoformat(),
                    "api_calls": reader.calls,
                    "probe_errors": probe_errors,
                    "failing": [r.to_dict() for r in rows if r.fails],
                    "gated": [r.to_dict() for r in rows if r.status == STATUS_GATED],
                    "jobs": [r.to_dict() for r in rows],
                },
                indent=2,
            )
        )
    else:
        print(render_text(rows, start, end))
        if probe_errors:
            print("\nthe check could not read some jobs:", file=sys.stderr)
            for err in probe_errors:
                print(f"  {err}", file=sys.stderr)

    failing = [r for r in rows if r.fails]
    if failing:
        print(
            f"\n{len(failing)} job(s) produced no or too few runs: "
            + ", ".join(r.job.id for r in failing),
            file=sys.stderr,
        )
        return FAIL
    if probe_errors:
        return PROBE_ERROR
    return OK


if __name__ == "__main__":
    raise SystemExit(main())