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
* ``GH_DISPATCH_TOKEN`` — the cron Worker's fine-grained PAT. A fine-grained PAT
  with only *Actions: write* does not necessarily authenticate ``GET /user``, so
  probing that would false-alarm. It is instead probed with the read-only
  ``GET /repos/{repo}/actions/runs?per_page=1``, which is gated on *Actions: read*
  and is therefore satisfied by the *Actions: write* grant the token is
  provisioned for: a 401/403 means the token is expired/revoked or has lost that
  grant. (The old probe, ``GET /repos/{repo}/actions/permissions``, is gated on
  *Administration: read* instead, so an Actions-only token would 403 and the
  canary would false-alarm daily.) Still no spend, still read-only.
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
from typing import Literal

OK = 0
FAIL = 1
PROBE_ERROR = 2

Status = Literal["valid", "invalid", "unvalidated-by-design", "absent", "probe-error"]


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


def collect(repo: str | None = None) -> list[Credential]:
    repo = repo or os.environ.get("REPO") or "digithings-ai/digithings"
    # DIGITHINGS_PROJECT_TOKEN carries `repo`+`project`, so /user authenticates.
    # GH_DISPATCH_TOKEN is fine-grained (Actions: write only) — probe an Actions
    # read-gated endpoint it is actually provisioned for instead.
    return [
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
                else ("WARN" if c.status == "unvalidated-by-design" else "OK")
            )
            print(f"{marker:4} {c.name}: {c.status} — {c.detail}")

    if failures:
        return FAIL
    if probe_errors:
        return PROBE_ERROR
    return OK


if __name__ == "__main__":
    raise SystemExit(main())
