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

# Deployment states that mean "created but not finished". GitHub's deployment
# state machine: pending -> in_progress -> success/failure/error, with queued
# used for waiting-on-concurrency. `inactive` and `success` are done.
UNFINISHED_STATES = frozenset({"pending", "queued", "in_progress", "waiting"})

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


def unfinished_deployments(deployments: list[dict[str, Any]]) -> list[dict[str, Any]]:
    """Filter raw deployments API rows down to the still-waiting ones."""
    return [d for d in deployments if str(d.get("state", "")) in UNFINISHED_STATES]


def stale_deployments(
    deployments: list[dict[str, Any]],
    *,
    now: datetime,
    max_age_minutes: int = DEFAULT_MAX_AGE_MINUTES,
    environment: str = DEFAULT_ENVIRONMENT,
) -> list[StaleDeployment]:
    """Unfinished deployments for ``environment`` older than ``max_age_minutes``.

    Sorted oldest-first: the top entry is the longest-standing gate wait and is
    what a human needs to see first.
    """
    cutoff = now - timedelta(minutes=max_age_minutes)
    stale: list[StaleDeployment] = []
    for row in unfinished_deployments(deployments):
        env = str(row.get("environment") or "")
        if env and environment and env != environment:
            continue
        try:
            created = _parse_timestamp(str(row.get("created_at") or ""))
        except ValueError:
            # An unparseable created_at is not evidence of a fresh deploy.
            # Skip it rather than crash the watchdog.
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
                state=str(row.get("state") or ""),
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
        "1. Review the pending deployment's checks:",
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
    """Read unfinished deployments for ``environment`` from the GitHub API."""
    raw = _gh(
        [
            "api",
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
    try:
        client.send_message(to=recipient, subject=subject, text_body=body)
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
    except GateCheckFailed as exc:
        # Fail closed: an unreadable gate is not an empty gate.
        print(f"GATE_CHECK_FAILED: {exc}", file=sys.stderr)
        return 2

    stale = stale_deployments(
        deployments,
        now=now,
        max_age_minutes=args.max_age_minutes,
        environment=args.environment,
    )
    if not stale:
        unfinished = len(unfinished_deployments(deployments))
        print(
            f"gate healthy: {unfinished} deployment(s) pending on "
            f"`{args.environment}`, none older than {args.max_age_minutes} min"
        )
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

    try:
        print(file_or_update_issue(args.repo, body, token, dry_run=args.dry_run))
    except GateCheckFailed as exc:
        print(f"issue upsert failed: {exc}", file=sys.stderr)
        return 2
    print(
        notify_email(
            f"{ISSUE_TITLE_PREFIX} {len(stale)} pending over gate", body, dry_run=args.dry_run
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
