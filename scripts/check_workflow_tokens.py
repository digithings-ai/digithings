#!/usr/bin/env python3
"""Token-validity canary for scheduled-workflow credentials (#3522).

Scheduled workflows fail *correlated* when a credential expires: every job that
reads it goes red at once, and the only signal today is the weekly
``workflow-health`` digest — up to seven days late. This script is the cheap,
non-destructive probe that surfaces the same failure in ≤24h.

What each credential gets, and why
----------------------------------
* ``DIGITHINGS_PROJECT_TOKEN`` — a GitHub PAT. Validated live and **without
  spend** with ``GET /user`` (a 401 means expired/revoked; a 200 proves it
  authenticates). This is the widest-blast-radius CI credential and the one the
  proposal actually names.
* ``GH_DISPATCH_TOKEN`` — the cron Worker's fine-grained PAT (``digithings-cron-dispatch``),
  provisioned for *Actions: write* plus *Issues: read and write* on
  ``digithings-ai/digithings`` and ``digithings-ai/twelve-x``. A fine-grained PAT
  does not necessarily authenticate ``GET /user``, so probing that would false-alarm.
  It is instead probed with the read-only
  ``GET /repos/{repo}/actions/runs?per_page=1``, which is gated on *Actions: read*
  and is therefore satisfied by the *Actions: write* grant the token is
  provisioned for: a 401/403 means the token is expired/revoked or has lost that
  grant. (The old probe, ``GET /repos/{repo}/actions/permissions``, is gated on
  *Administration: read* instead, so an Actions-only token would 403 and the
  canary would false-alarm daily.) Still no spend, still read-only.
* ``GH_DISPATCH_TOKEN`` also carries **Issues: read and write** (added
  2026-10-04, ``78b69c90d``), and DIG-71's digest alarm depends on the write
  half. The Actions probe above cannot see that grant go missing at all, so the
  canary proves it separately (DIG-362) — see :func:`probe_issues_write_grant`.
  A read probe provably cannot do this job: GitHub offers only *no access* /
  *read* / *read and write* for Issues, so a token downgraded to read-only still
  satisfies an ``issues: read`` check. Fine-grained PAT permissions are not
  readable over the API either — only a real write proves them. The probe
  therefore POSTs one marker comment to a dedicated pinned issue
  (``TOKEN_CANARY_PROBE_ISSUE``) and DELETEs it, **weekly**, so watcher
  notifications stay near zero. It spends nothing and leaves nothing: a failed
  DELETE is reported as a failure rather than hidden, because a marker left
  behind breaks the probe's own promise. The cheap ``GET /issues/{n}`` read
  probe runs alongside it so the failure output distinguishes *grant removed*
  (read fails too) from *grant downgraded* (read passes, write fails) — the
  state DIG-93 wrongly believed the token was in.
* ``CLAUDE_CODE_OAUTH_TOKEN`` / ``CURSOR_API_KEY`` — Claude Code Max / Cursor
  org secrets. **Neither has a documented, quota-free introspection endpoint.**
  Proving either is valid requires an actual agent invocation, which is exactly
  what #3522's acceptance criteria forbid ("never a full agent run"). So this
  script only asserts presence + non-trivial shape for these two and marks them
  ``unvalidated-by-design`` in its output; it does **not** claim they are valid.
  Making them properly checkable needs a product/owner decision (see #3522
  comment) — a dedicated low-cost probe endpoint, or accepting a tiny weekly
  spend, or an owner-attested rotation log.

Exit codes
----------
``0`` — every credential the script *can* verify is valid, and the unverifiable
ones are present. ``1`` — a verified credential failed (expired/revoked or
missing), which is the state that should file a tracker. ``2`` — the probe
itself could not run (e.g. ``gh`` unavailable), reported but not treated as a
credential failure. ``--json`` emits the same verdict for the workflow to parse.

Usage
-----
::

    python3 scripts/check_workflow_tokens.py
    python3 scripts/check_workflow_tokens.py --json
"""

from __future__ import annotations

import argparse
import json
import os
import subprocess
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Literal

OK = 0
FAIL = 1
PROBE_ERROR = 2

Status = Literal[
    "valid",
    "invalid",
    "unvalidated-by-design",
    "absent",
    "probe-error",
    "skipped-by-design",
]


@dataclass
class Credential:
    name: str
    status: Status
    detail: str
    verifiable: bool = True
    env: dict[str, str] = field(default_factory=dict)

    @property
    def is_failure(self) -> bool:
        # Only a verifiable credential in a bad state is a failure. An
        # "unvalidated-by-design" org token is not — that is a known gap, not a
        # regression, and must never be what files the tracker.
        return self.verifiable and self.status in {"invalid", "absent"}


def _gh_api(endpoint: str, token: str, jq: str = ".login") -> tuple[int, str]:
    """Return (exit_code, stderr-or-empty) for a read-only ``gh api`` call."""
    env = {**os.environ, "GH_TOKEN": token}
    try:
        proc = subprocess.run(
            ["gh", "api", endpoint, "--jq", jq],
            capture_output=True,
            text=True,
            env=env,
            timeout=30,
        )
    except FileNotFoundError:
        return PROBE_ERROR, "gh CLI not found"
    except subprocess.TimeoutExpired:
        return PROBE_ERROR, f"gh api {endpoint} timed out"
    if proc.returncode == 0:
        return 0, ""
    return FAIL, (proc.stderr or proc.stdout or "").strip()[:200]


def check_github_pat(
    name: str, token: str | None, *, endpoint: str = "/user", jq: str = ".login"
) -> Credential:
    if not token:
        return Credential(name, "absent", "secret not set", env={name: "absent"})
    code, err = _gh_api(endpoint, token, jq)
    if code == 0:
        return Credential(name, "valid", f"GET {endpoint} authenticated")
    if code == PROBE_ERROR:
        return Credential(name, "probe-error", err)
    return Credential(name, "invalid", f"GET {endpoint} failed: {err}")


def _gh_api_write(
    endpoint: str, token: str, *, method: str, fields: dict[str, str] | None = None
) -> tuple[int, str, str]:
    """Return ``(exit_code, stdout, stderr)`` for a *writing* ``gh api`` call.

    Separate from :func:`_gh_api` on purpose: read probes only ever need a
    boolean, but the Issues write probe must read back the created comment's id
    so it can delete it again. ``fields`` become ``-f`` flags, which keeps the
    payload out of argv quoting entirely.
    """
    argv = ["gh", "api", endpoint, "-X", method]
    for key, value in (fields or {}).items():
        argv += ["-f", f"{key}={value}"]
    env = {**os.environ, "GH_TOKEN": token}
    try:
        proc = subprocess.run(argv, capture_output=True, text=True, env=env, timeout=30)
    except FileNotFoundError:
        return PROBE_ERROR, "", "gh CLI not found"
    except subprocess.TimeoutExpired:
        return PROBE_ERROR, "", f"gh api {endpoint} timed out"
    if proc.returncode == 0:
        return 0, proc.stdout or "", ""
    return FAIL, "", (proc.stderr or proc.stdout or "").strip()[:200]


#: The marker body. Kept short and self-explaining: if cleanup ever fails, the
#: comment left behind has to tell an operator what created it and that it is
#: safe to delete.
_PROBE_MARKER = (
    "Token-canary write probe for `GH_DISPATCH_TOKEN` (DIG-362). "
    "Created and immediately deleted by the Ops token-validity canary to prove "
    "the Issues: write grant. No action needed."
)


def probe_issues_write_grant(name: str, token: str | None, repo: str, issue: int) -> Credential:
    """Prove ``token`` holds Issues **write** by writing and deleting a comment.

    A read probe cannot do this job. GitHub offers exactly three levels for
    Issues — *no access*, *read*, *read and write* — so ``GET /issues/{n}``
    passes on a token that has been **downgraded** to read-only, which is the
    exact state DIG-93 wrongly believed the token was in. Only a real write
    separates "grant removed" from "grant downgraded".

    Costs nothing and leaves nothing: one comment, then ``DELETE`` on it. The
    DELETE is verified, and a failed DELETE is itself a failure — a marker left
    on the pinned issue violates the probe's own promise, so it must be loud.
    """
    if not token:
        return Credential(name, "absent", "secret not set", env={name: "absent"})

    comments = f"/repos/{repo}/issues/{issue}/comments"

    # Step 1 — a real write. POST the marker.
    code, out, err = _gh_api_write(comments, token, method="POST", fields={"body": _PROBE_MARKER})
    if code == PROBE_ERROR:
        return Credential(name, "probe-error", err)
    if code != 0:
        # A 403 here is the signal: the token can no longer write. Name it,
        # because "invalid" alone does not say which grant went missing.
        return Credential(
            name,
            "invalid",
            f"Issues: write grant LOST — POST {comments} was rejected: {err}",
        )

    # Step 2 — self-clean. DELETE what we just created.
    try:
        comment_id = json.loads(out)["id"]
    except (json.JSONDecodeError, KeyError, TypeError):
        return Credential(
            name,
            "probe-error",
            f"POST {comments} succeeded but returned no comment id; "
            "a marker comment may have been left behind",
        )

    code, _out, err = _gh_api_write(f"/repos/{repo}/issues/comments/{comment_id}", token, method="DELETE")
    if code != 0:
        # The grant is proven, but cleanup failed. Both facts get reported, and
        # this stays a failure so the leftover comment is actually dealt with.
        return Credential(
            name,
            "invalid",
            f"Issues: write grant OK, but the marker comment {comment_id} could NOT be "
            f"deleted from {repo}#{issue} and must be removed by hand: {err}",
        )
    return Credential(
        name,
        "valid",
        f"Issues: write grant proven (comment {comment_id} posted and deleted on {repo}#{issue})",
    )


def check_unverifiable(name: str, token: str | None, why: str) -> Credential:
    if not token:
        return Credential(name, "absent", "secret not set", verifiable=False)
    if len(token) < 20:
        return Credential(name, "absent", "value present but implausibly short", verifiable=False)
    return Credential(
        name,
        "unvalidated-by-design",
        why,
        verifiable=False,
    )


#: Presence of a value is all we can assert without an agent run. Kept short
#: because the output is posted verbatim into the tracker issue.
_CLAUDE_WHY = (
    "no quota-free introspection endpoint; proving validity needs an agent run (forbidden by #3522)"
)
_CURSOR_WHY = (
    "no quota-free introspection endpoint; proving validity needs an agent run (forbidden by #3522)"
)


def _probe_day_due(now: datetime | None = None) -> bool:
    """True once a week, on ``TOKEN_CANARY_PROBE_WEEKDAY`` (UTC, default Sunday).

    The write probe posts and deletes a real comment, which fires watcher
    notifications. Weekly keeps that volume near zero while still satisfying
    "proves the grant at least weekly" — the ceiling on detection latency.
    """
    raw = os.environ.get("TOKEN_CANARY_PROBE_WEEKDAY", "7")
    try:
        weekday = int(raw)
    except ValueError:
        weekday = 7
    if not 1 <= weekday <= 7:
        weekday = 7
    return (now or datetime.now(timezone.utc)).isoweekday() == weekday


def _probe_issue_number() -> int | None:
    """The pinned issue the write probe targets, or ``None`` if unconfigured."""
    raw = os.environ.get("TOKEN_CANARY_PROBE_ISSUE", "").strip()
    return int(raw) if raw.isdigit() and int(raw) > 0 else None


def collect(repo: str | None = None) -> list[Credential]:
    repo = repo or os.environ.get("REPO") or "digithings-ai/digithings"
    # DIGITHINGS_PROJECT_TOKEN carries `repo`+`project`, so /user authenticates.
    # GH_DISPATCH_TOKEN is fine-grained (Actions: write, Issues: read/write) — probe
    # an Actions read-gated endpoint it is actually provisioned for instead.
    creds = [
        check_github_pat("DIGITHINGS_PROJECT_TOKEN", os.environ.get("DIGITHINGS_PROJECT_TOKEN")),
        check_github_pat(
            "GH_DISPATCH_TOKEN",
            os.environ.get("GH_DISPATCH_TOKEN"),
            endpoint=f"/repos/{repo}/actions/runs?per_page=1",
            jq=".total_count",
        ),
        check_unverifiable(
            "CLAUDE_CODE_OAUTH_TOKEN", os.environ.get("CLAUDE_CODE_OAUTH_TOKEN"), _CLAUDE_WHY
        ),
        check_unverifiable("CURSOR_API_KEY", os.environ.get("CURSOR_API_KEY"), _CURSOR_WHY),
    ]
    creds.append(_issues_grant_probe(repo))
    return creds


#: Name of the synthetic credential that reports on the Issues grant, so a lost
#: grant is attributable even though it is the same token as the Actions probe.
ISSUES_GRANT_PROBE = "GH_DISPATCH_TOKEN (issues: write)"


def _issues_grant_probe(repo: str) -> Credential:
    """Pair a cheap read probe with the weekly write probe (DIG-362).

    The read probe alone cannot detect a downgrade — GitHub offers only *no
    access* / *read* / *read and write* for Issues, and a downgraded token
    satisfies ``issues: read``. Run next to the write probe it earns its place:
    read-pass + write-fail is reported as *downgraded to read-only*, whereas
    read-fail + write-fail is *grant removed*. Without it both are a bare 403.
    """
    token = os.environ.get("GH_DISPATCH_TOKEN")
    issue = _probe_issue_number()
    if issue is None:
        return Credential(
            ISSUES_GRANT_PROBE,
            "skipped-by-design",
            "TOKEN_CANARY_PROBE_ISSUE is not set; the Issues grant is unproven "
            "(set it to a dedicated pinned issue number to arm this probe)",
            verifiable=False,
        )
    if not _probe_day_due():
        return Credential(
            ISSUES_GRANT_PROBE,
            "skipped-by-design",
            f"not the probe weekday; the write probe runs weekly on "
            f"TOKEN_CANARY_PROBE_WEEKDAY ({(datetime.now(timezone.utc) + _days_ahead()).strftime('%A')})",
            verifiable=False,
        )

    read_only = check_github_pat(
        ISSUES_GRANT_PROBE,
        token,
        endpoint=f"/repos/{repo}/issues/{issue}",
        jq=".number",
    )
    write = probe_issues_write_grant(ISSUES_GRANT_PROBE, token, repo, issue)

    # The write verdict wins: it is the only probe that can see a downgrade.
    if write.status != "valid":
        if read_only.status == "valid":
            write.detail = (
                f"{write.detail}. The Issues: READ probe passed, so the grant was not "
                f"removed — it was DOWNGRADED to read-only, which is what breaks DIG-71's alarm."
            )
        return write
    if read_only.status == "invalid":
        # Contradiction: a write landed but a read 403'd. Say so rather than
        # reporting a green probe on inconsistent evidence.
        return Credential(
            ISSUES_GRANT_PROBE,
            "invalid",
            f"INCONSISTENT — write probe succeeded but the Issues: read probe failed: "
            f"{read_only.detail}",
        )
    return write


def _days_ahead():
    from datetime import timedelta

    raw = os.environ.get("TOKEN_CANARY_PROBE_WEEKDAY", "7")
    try:
        weekday = int(raw)
    except ValueError:
        weekday = 7
    if not 1 <= weekday <= 7:
        weekday = 7
    now = datetime.now(timezone.utc)
    return timedelta(days=(weekday - now.isoweekday()) % 7)


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--json", action="store_true", help="emit machine-readable verdict")
    args = parser.parse_args()

    creds = collect()
    failures = [c for c in creds if c.is_failure]
    probe_errors = [c for c in creds if c.status == "probe-error"]

    if args.json:
        print(
            json.dumps(
                {
                    "credentials": [asdict(c) for c in creds],
                    "failures": [c.name for c in failures],
                    "probe_errors": [c.name for c in probe_errors],
                },
                indent=2,
            )
        )
    else:
        for c in creds:
            marker = (
                "FAIL"
                if c.is_failure
                else (
                    "WARN"
                    if c.status in {"unvalidated-by-design", "skipped-by-design"}
                    else "OK"
                )
            )
            print(f"{marker:4} {c.name}: {c.status} — {c.detail}")

    if failures:
        return FAIL
    if probe_errors:
        return PROBE_ERROR
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
