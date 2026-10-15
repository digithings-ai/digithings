#!/usr/bin/env python3
"""Alert when a production deployment sits on the environment gate too long.

DIG-1569. The stack deploy workflow had no ``push`` trigger, so merges to main
deployed nothing (fixed in the same change). The companion defect this script
covers is the quiet one: a deployment can start correctly and then wait on the
``production`` environment's approval gate indefinitely, with nothing to say so.
On DIG-1484 three production deployments were pending approval for 14.5h, 6h
and 0h while production still served the container that exposed unmasked
customer PII. A pending deployment is not a neutral state — it is an
unremediated exposure that reads as "handled" in the git history.

So: a deployment that is *still pending* past ``--max-age-minutes`` (default 60)
is an incident, not a queue.

Design notes
------------
* Pure core, thin shell. :func:`stale_deployments` and :func:`render_issue_body`
  take plain data and are unit-tested without network or secrets; :func:`main`
  only wires ``gh api`` and the notifier to them.
* A deployment's progress is read from its **latest status**, not from the
  deployment object. On digithings the deployments list payload has no ``state``
  key at all and the per-deployment GET returns ``"state": null``, so classifying
  on the deployment's own ``state`` matches nothing and reports a healthy gate
  while deployments sit on it. See :func:`apply_latest_statuses`.
* Fails **closed** on an unreadable deployments API: if we cannot see the gate,
  we cannot claim the gate is healthy. Exit 2 with the reason, never exit 0
  with "no stale deployments" from an empty result that is actually a failure.
* Never prints a token. ``gh`` is invoked with the ambient ``GH_TOKEN`` rather
  than an argument, and the notifier reports missing env *names* only.
* Alerts by filing/updating one GitHub issue (deduplicated on a stable marker
  line, so a 60-minute cadence reuses one issue instead of filing a new one
  every 30 minutes) plus an optional email. Both channels are best-effort for
  the email and authoritative for the issue, because an email transport
  outage must not suppress the issue.

Usage
-----
    python scripts/production_deploy_gate_latency.py --max-age-minutes 60
    python scripts/production_deploy_gate_latency.py --dry-run
"""

from __future__ import annotations

import argparse
import html
import json
import os
import subprocess
import sys
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from pathlib import Path
from typing import Any

REPO_ROOT = Path(__file__).resolve().parents[1]
if str(REPO_ROOT) not in sys.path:
    sys.path.insert(0, str(REPO_ROOT))

# These are **status** states, not deployment-object states. A deployment's own
# `state` is unusable here (null on every digithings deployment), so progress is
# read from the deployment's latest status instead.
#
# `waiting` is the state the environment-approval gate reports; the others are
# GitHub's own lifecycle states. `inactive` and `success` are done.
UNFINISHED_STATES = frozenset({"pending", "queued", "in_progress", "waiting"})

# The only states that mean "this deployment will never move again on its own".
# Anything not in here counts as unfinished, including a blank state and any state
# GitHub adds later: we cannot claim a gate is healthy from a state we do not
# recognise, so an unknown state alerts rather than passing.
DONE_STATES = frozenset({"success", "failure", "error", "inactive"})

# Deployments created longer ago than this are never on the gate, so their status
# is not worth an API call. The watchdog runs every 30 minutes, so a 24h lookback
# is ~48 ticks of coverage against a deployment that vanished from the API.
LOOKBACK_HOURS = 24

ISSUE_TITLE_PREFIX = "[ops:deploy-gate]"
# Stable marker: the issue-update step searches for exactly this so the watchdog
# reuses one open issue per repository instead of filing a new one per tick.
ISSUE_MARKER = "<!-- dig-production-deploy-gate-watchdog -->"

DEFAULT_MAX_AGE_MINUTES = 60
DEFAULT_REPO = "digithings-ai/digithings"
DEFAULT_ENVIRONMENT = "production"


class GateCheckFailed(RuntimeError):
    """The gate could not be inspected — fail closed, never 'all clear'."""


@dataclass(frozen=True)
class StaleDeployment:
    """One deployment that has been waiting on approval past the threshold."""

    deployment_id: int
    sha: str
    ref: str
    environment: str
    state: str
    created_at: datetime
    age_minutes: int
    creator: str

    @property
    def short_sha(self) -> str:
        return self.sha[:8] if self.sha else "unknown"

    def to_json(self) -> dict[str, Any]:
        return {
            "deployment_id": self.deployment_id,
            "sha": self.sha,
            "short_sha": self.short_sha,
            "ref": self.ref,
            "environment": self.environment,
            "state": self.state,
            "created_at": self.created_at.isoformat(),
            "age_minutes": self.age_minutes,
            "creator": self.creator,
        }


def _parse_timestamp(value: str) -> datetime:
    text = (value or "").strip()
    if not text:
        raise ValueError("empty timestamp")
    if text.endswith("Z"):
        text = text[:-1] + "+00:00"
    parsed = datetime.fromisoformat(text)
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=UTC)
    return parsed.astimezone(UTC)


def effective_state(deployment_state: Any, latest_status_state: Any) -> str:
    """Combine a deployment's own state with its latest status into one state.

    The status wins: it is the only field on digithings that carries progress. A
    blank result is normalised to ``unknown`` rather than ``""`` so it is obvious
    in an alert that we could not read the state at all.
    """
    for candidate in (latest_status_state, deployment_state):
        text = str(candidate or "").strip().lower()
        if text:
            return text
    return "unknown"


def is_unfinished(state: Any) -> bool:
    """True unless the state is one that means the deployment is finished.

    Deliberately a deny-list and not an allow-list of :data:`UNFINISHED_STATES`:
    a state we have not seen before is not evidence of success, so it alerts.
    """
    text = str(state or "").strip().lower()
    if text in DONE_STATES:
        return False
    return True


def within_lookback(
    deployments: list[dict[str, Any]],
    *,
    now: datetime,
    lookback_hours: int = LOOKBACK_HOURS,
) -> list[dict[str, Any]]:
    """Rows recent enough that a gate stall is still plausible.

    This bound is a *precondition for examination*, not a filter applied after it,
    and the distinction is load-bearing. Rows outside the window are never given a
    status (see :func:`resolve_status_states`), so they carry no ``state`` at all —
    and an absent state means "unresolved", which :func:`is_unfinished` deliberately
    treats as unfinished. Filtering after classification therefore reported every
    deployment in the repository's history as stalled: 149 phantom alerts on the
    first live run, the oldest 102 days finished.
    """
    floor = now - timedelta(hours=lookback_hours)
    recent: list[dict[str, Any]] = []
    for row in deployments:
        try:
            created = _parse_timestamp(str(row.get("created_at") or ""))
        except ValueError:
            continue
        if created >= floor:
            recent.append(row)
    return recent


def unfinished_deployments(
    deployments: list[dict[str, Any]],
    *,
    now: datetime,
    lookback_hours: int = LOOKBACK_HOURS,
) -> list[dict[str, Any]]:
    """Filter deployments API rows down to the ones still waiting on the gate.

    Rows are expected to have been through :func:`apply_latest_statuses` first; a
    raw digithings row has no ``state`` at all and lands here as ``unknown``,
    which counts as unfinished rather than silently healthy. Rows older than the
    lookback window are excluded first — a deployment cannot still be on the gate
    24 hours after it was created.
    """
    return [
        d
        for d in within_lookback(deployments, now=now, lookback_hours=lookback_hours)
        if is_unfinished(d.get("state"))
    ]


def stale_deployments(
    deployments: list[dict[str, Any]],
    *,
    now: datetime,
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
    environment: str = DEFAULT_ENVIRONMENT,
    lookback_hours: int = LOOKBACK_HOURS,
) -> list[StaleDeployment]:
    """Unfinished deployments for ``environment`` older than ``max_age_minutes``.

    Sorted oldest-first: the top entry is the longest-standing gate wait and is
    what a human needs to see first.
    """
    cutoff = now - timedelta(minutes=max_age_minutes)
    stale: list[StaleDeployment] = []
    for row in unfinished_deployments(deployments, now=now, lookback_hours=lookback_hours):
        env = str(row.get("environment") or "")
        if env and environment and env != environment:
            continue
        try:
            created = _parse_timestamp(str(row.get("created_at") or ""))
        except ValueError:
            # An unparseable created_at makes the row's age unknowable, so we can
            # neither call it stale nor call it fresh. This one row is dropped
            # rather than crashing the watchdog or alerting on garbage — a
            # deliberate, narrow fail-open, recorded here so it is not mistaken for
            # the module's wider fail-closed stance. Rows past the lookback window
            # are dropped earlier by the same timestamp parse.
            continue
        if created > cutoff:
            continue
        age_minutes = int((now - created).total_seconds() // 60)
        stale.append(
            StaleDeployment(
                deployment_id=int(row.get("id") or 0),
                sha=str(row.get("sha") or ""),
                ref=str(row.get("ref") or ""),
                environment=env or environment,
                state=effective_state(row.get("state"), None),
                created_at=created,
                age_minutes=age_minutes,
                creator=str((row.get("creator") or {}).get("login") or "unknown"),
            )
        )
    stale.sort(key=lambda d: d.created_at)
    return stale


def render_issue_body(
    stale: list[StaleDeployment],
    *,
    max_age_minutes: int,
    repo: str,
    environment: str = DEFAULT_ENVIRONMENT,
) -> str:
    """Markdown body for the gate-latency issue."""
    lines = [
        ISSUE_MARKER,
        "## A production deployment is waiting on the `production` gate",
        "",
        f"**Environment:** `{environment}`  ",
        f"**Threshold:** {max_age_minutes} minutes  ",
        f"**Waiting deployments:** {len(stale)}",
        "",
        "A deployment listed here started, passed its checks, and is waiting on "
        "human approval. Nothing ships until it is approved or rejected, and "
        "until then **production is serving the previous build**. If the previous "
        "build is the one carrying the fix you are waiting on, the fix is not "
        "live.",
        "",
        "| Created | Age | State | Ref | Commit | Creator |",
        "|---|---|---|---|---|---|",
    ]
    for item in stale:
        lines.append(
            f"| {item.created_at.strftime('%Y-%m-%d %H:%M UTC')} "
            f"| **{item.age_minutes} min** "
            f"| `{item.state}` "
            f"| `{item.ref}` "
            f"| `{item.short_sha}` "
            f"| @{item.creator} |"
        )
    lines += [
        "",
        "## What to do",
        "",
        "1. Review the checks and diff for each deployment below:",
        "",
    ]
    lines += [
        f"   - [`{item.short_sha}` on `{item.ref}`]"
        f"(https://github.com/{repo}/commit/{item.sha})"
        f" — deployment [{item.deployment_id}]"
        f"(https://github.com/{repo}/deployments/{item.deployment_id})"
        for item in stale
    ]
    lines += [
        "",
        "2. Approve or reject it at the environment gate — the deploy stays parked "
        "until a human answers.",
        "3. If this deployment is not wanted, reject it and confirm nothing newer "
        "is also parked behind it.",
        "",
        f"Pending deployments for `{environment}`: {f'https://github.com/{repo}/deployments'}",
    ]
    return "\n".join(lines) + "\n"


def _gh(args: list[str], *, token: str | None, stdin: str | None = None) -> str:
    """Run `gh` with the token in the environment, never in argv.

    ``stdin`` is passed through for ``--body-file -``: multi-line issue bodies go
    over the pipe rather than through argv or command substitution, so quoting
    and injection are not a concern.
    """
    env = dict(os.environ)
    if token:
        env["GH_TOKEN"] = token
    proc = subprocess.run(
        ["gh", *args],
        capture_output=True,
        text=True,
        input=stdin,
        env=env,
        check=False,
    )
    if proc.returncode != 0:
        detail = (proc.stderr or proc.stdout or "").strip().splitlines()
        tail = detail[-1] if detail else f"exit {proc.returncode}"
        raise GateCheckFailed(f"gh {' '.join(args[:2])} failed: {tail}")
    return proc.stdout


def fetch_deployments(repo: str, environment: str, token: str | None) -> list[dict[str, Any]]:
    """Read deployments for ``environment`` from the GitHub API.

    ``--method GET`` is mandatory, not cosmetic. Passing any ``-f/--raw-field``
    makes ``gh api`` switch to POST, so the server sees a create-deployment request
    and answers ``422 "ref" wasn't supplied`` — on every run, forever. The filter
    parameters therefore have to be explicit about the verb.
    """
    raw = _gh(
        [
            "api",
            "--method",
            "GET",
            "--paginate",
            f"repos/{repo}/deployments",
            "-f",
            f"environment={environment}",
            "-f",
            "per_page=100",
        ],
        token=token,
    )
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise GateCheckFailed(f"deployments API returned unparseable JSON: {exc}") from exc
    if isinstance(payload, dict):  # --paginate on a list endpoint yields a list
        payload = [payload]
    if not isinstance(payload, list):
        raise GateCheckFailed("deployments API returned an unexpected shape")
    return [row for row in payload if isinstance(row, dict)]


def _latest_status_state(statuses_url: str, token: str | None) -> str:
    """State of a deployment's most recent status, or ``""`` if it has none."""
    raw = _gh(
        ["api", "--method", "GET", statuses_url, "-f", "per_page=1"],
        token=token,
    )
    try:
        payload = json.loads(raw or "[]")
    except json.JSONDecodeError as exc:
        raise GateCheckFailed(f"statuses API returned unparseable JSON: {exc}") from exc
    if isinstance(payload, dict):
        payload = [payload]
    if not isinstance(payload, list):
        raise GateCheckFailed("statuses API returned an unexpected shape")
    if not payload:
        return ""
    newest = payload[0]
    if not isinstance(newest, dict):
        return ""
    return str(newest.get("state") or "")


def apply_latest_statuses(
    deployments: list[dict[str, Any]],
    latest_states: dict[int, str],
) -> list[dict[str, Any]]:
    """Return copies of ``deployments`` with a resolved ``state`` field.

    ``latest_states`` maps deployment id to that deployment's newest status state,
    as read by :func:`resolve_status_states`. Rows are copied, never mutated, so the
    caller's API payload stays usable for diagnostics.

    A deployment with no statuses at all resolves to ``pending``: it was created and
    never reported progress, which for an environment-gated deployment is exactly a
    deployment sitting on the gate.
    """
    resolved: list[dict[str, Any]] = []
    for row in deployments:
        dep_id = int(row.get("id") or 0)
        status_state = latest_states.get(dep_id, "")
        merged = dict(row)
        merged["state"] = effective_state(row.get("state"), status_state) or "unknown"
        resolved.append(merged)
    return resolved


def resolve_status_states(
    deployments: list[dict[str, Any]],
    token: str | None,
    *,
    now: datetime,
    lookback_hours: int = LOOKBACK_HOURS,
) -> dict[int, str]:
    """Read the newest status for each recent deployment.

    Bounded twice over: deployments created before ``now - lookback_hours`` are
    skipped (a deployment that old is not still on the gate), and each read is a
    single ``per_page=1`` request. Deployments missing ``statuses_url`` or an
    unparseable ``created_at`` are skipped and resolve to ``pending`` downstream.
    """
    floor = now - timedelta(hours=lookback_hours)
    states: dict[int, str] = {}
    for row in deployments:
        dep_id = int(row.get("id") or 0)
        if not dep_id:
            continue
        try:
            created = _parse_timestamp(str(row.get("created_at") or ""))
        except ValueError:
            continue
        if created < floor:
            continue
        statuses_url = str(row.get("statuses_url") or "").strip()
        if not statuses_url:
            continue
        states[dep_id] = _latest_status_state(statuses_url, token)
    return states


def find_open_issue(repo: str, token: str | None) -> int | None:
    """Number of the open watchdog issue, if one exists (dedup on the marker)."""
    raw = _gh(
        [
            "issue",
            "list",
            "--repo",
            repo,
            "--state",
            "open",
            "--search",
            f"in:title {ISSUE_TITLE_PREFIX}",
            "--json",
            "number,body",
            "--limit",
            "20",
        ],
        token=token,
    )
    try:
        rows = json.loads(raw or "[]")
    except json.JSONDecodeError:
        return None
    for row in rows if isinstance(rows, list) else []:
        if ISSUE_MARKER in str(row.get("body") or ""):
            return int(row.get("number") or 0) or None
    return None


def file_or_update_issue(repo: str, body: str, token: str | None, *, dry_run: bool) -> str:
    """Reuse the open watchdog issue, or file a new one. Returns a URL/notice."""
    if dry_run:
        return f"dry-run: would file or update {ISSUE_TITLE_PREFIX} issue in {repo}"
    existing = find_open_issue(repo, token)
    if existing:
        _gh(
            ["issue", "edit", str(existing), "--repo", repo, "--body-file", "-"],
            token=token,
            stdin=body,
        )
        return f"updated https://github.com/{repo}/issues/{existing}"
    url = _gh(
        [
            "issue",
            "create",
            "--repo",
            repo,
            "--title",
            f"{ISSUE_TITLE_PREFIX} production deployment waiting on the gate",
            "--label",
            "priority:critical,component:root",
            "--body-file",
            "-",
        ],
        token=token,
        stdin=body,
    )
    return url.strip()


def resolve_watchdog_issue(repo: str, token: str | None, *, dry_run: bool) -> str:
    """Close the open watchdog issue once the gate is healthy again.

    A comment, not a silent close: the timeline of how long the gate held is the
    evidence for the incident review, and it is not recoverable from git history
    after the fact.
    """
    if dry_run:
        return f"dry-run: would comment and close {ISSUE_TITLE_PREFIX} issue in {repo}"
    existing = find_open_issue(repo, token)
    if not existing:
        return "gate healthy; no watchdog issue open"
    _gh(
        ["issue", "comment", str(existing), "--repo", repo, "--body-file", "-"],
        token=token,
        stdin=(
            f"{ISSUE_MARKER}\n"
            "**Resolved.** No production deployment is currently over the gate "
            "threshold. Closing this issue; a new stall files a new one."
        ),
    )
    _gh(["issue", "close", str(existing), "--repo", repo, "--reason", "completed"], token=token)
    return f"closed https://github.com/{repo}/issues/{existing} (gate recovered)"


def notify_email(subject: str, body: str, *, dry_run: bool) -> str:
    """Best-effort email via the Cloudflare Email Sending notifier.

    Returns a one-line status. A missing notification configuration is reported
    and *not* fatal — the issue is the authoritative channel.
    """
    if dry_run:
        return "dry-run: email not sent"
    try:
        from digiquant.notify.cloudflare_email import (
            NotifyNotConfiguredError,
            build_email_client,
            format_notify_not_configured,
        )
    except ImportError as exc:
        return f"email skipped: digiquant not importable ({exc})"
    try:
        client = build_email_client()
    except NotifyNotConfiguredError as exc:
        return format_notify_not_configured(exc.missing)
    if client is None:
        from digiquant.notify.cloudflare_email import missing_notify_env_names

        return format_notify_not_configured(missing_notify_env_names())
    recipient = os.environ.get("GATE_ALERT_EMAIL", "").strip()
    if not recipient:
        return "email skipped: GATE_ALERT_EMAIL not set"
    # `send_message` requires html_body positionally; omitting it raises TypeError,
    # which the broad except below would swallow into a one-line "email failed"
    # while the channel silently never worked.
    html_body = "<pre>" + html.escape(body) + "</pre>"
    try:
        client.send_message(to=recipient, subject=subject, text_body=body, html_body=html_body)
    except Exception as exc:
        return f"email failed: {type(exc).__name__}: {exc}"
    return f"email sent to {recipient}"


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.split("\n", 1)[0])
    parser.add_argument("--repo", default=os.environ.get("GATE_ALERT_REPO", DEFAULT_REPO))
    parser.add_argument(
        "--environment",
        default=os.environ.get("GATE_ALERT_ENVIRONMENT", DEFAULT_ENVIRONMENT),
    )
    parser.add_argument(
        "--max-age-minutes",
        type=int,
        default=int(os.environ.get("GATE_ALERT_MAX_AGE_MINUTES", DEFAULT_MAX_AGE_MINUTES)),
        help="Minutes a deployment may wait on the gate before it is an alert.",
    )
    parser.add_argument(
        "--lookback-hours",
        type=int,
        default=int(os.environ.get("GATE_ALERT_LOOKBACK_HOURS", LOOKBACK_HOURS)),
        help=(
            "How far back to read deployment statuses. Bounds the per-deployment API "
            "calls; a deployment older than this is not still on the gate."
        ),
    )
    parser.add_argument(
        "--now",
        default=os.environ.get("GATE_ALERT_NOW"),
        help="Override the current UTC time (ISO 8601). For tests.",
    )
    parser.add_argument("--dry-run", action="store_true")
    args = parser.parse_args(argv)

    now = _parse_timestamp(args.now) if args.now else datetime.now(UTC)
    token = os.environ.get("DIGITHINGS_PROJECT_TOKEN") or os.environ.get("GH_TOKEN") or None

    try:
        deployments = fetch_deployments(args.repo, args.environment, token)
        deployments = apply_latest_statuses(
            deployments,
            resolve_status_states(
                deployments,
                token,
                now=now,
                lookback_hours=args.lookback_hours,
            ),
        )
    except GateCheckFailed as exc:
        # Fail closed: an unreadable gate is not an empty gate.
        print(f"GATE_CHECK_FAILED: {exc}", file=sys.stderr)
        return 2

    stale = stale_deployments(
        deployments,
        now=now,
        max_age_minutes=args.max_age_minutes,
        environment=args.environment,
        lookback_hours=args.lookback_hours,
    )
    if not stale:
        unfinished = len(
            unfinished_deployments(deployments, now=now, lookback_hours=args.lookback_hours)
        )
        print(
            f"gate healthy: {unfinished} deployment(s) pending on "
            f"`{args.environment}`, none older than {args.max_age_minutes} min"
        )
        # Recovery has to close the filed issue. Without this the
        # `priority:critical` issue is opened on the first stall and stays open
        # forever, so "one critical open gate issue" stops meaning "the gate is
        # stalled" and the watchdog is muted by its own first true positive.
        try:
            print(resolve_watchdog_issue(args.repo, token, dry_run=args.dry_run))
        except GateCheckFailed as exc:
            # A gate that recovered but whose issue cannot be closed is worth a
            # non-zero exit -- the monitoring state is inconsistent -- but it must
            # not be reported as a stall.
            print(f"recovery note failed: {exc}", file=sys.stderr)
            return 2
        return 0

    body = render_issue_body(
        stale,
        max_age_minutes=args.max_age_minutes,
        repo=args.repo,
        environment=args.environment,
    )
    longest = stale[0]
    print(
        f"gate stalled: {len(stale)} deployment(s) pending on "
        f"`{args.environment}`, oldest {longest.age_minutes} min "
        f"({longest.short_sha} on {longest.ref})"
    )
    print(json.dumps([item.to_json() for item in stale], indent=2))

    # The two channels are independent: neither may suppress the other. An earlier
    # draft returned early on an issue-API failure, so a GitHub outage took out the
    # email too and both channels went dark at exactly the moment they mattered.
    issue_status = "issue not filed"
    try:
        issue_status = file_or_update_issue(args.repo, body, token, dry_run=args.dry_run)
    except GateCheckFailed as exc:
        issue_status = f"issue upsert FAILED: {exc}"
    print(issue_status)
    print(
        notify_email(
            f"{ISSUE_TITLE_PREFIX} {len(stale)} pending over gate", body, dry_run=args.dry_run
        )
    )
    return 2 if issue_status.startswith("issue upsert FAILED") else 0


if __name__ == "__main__":
    raise SystemExit(main())
