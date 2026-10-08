#!/usr/bin/env python3
"""Classify CI ``needs`` results for the ``required-checks`` aggregator job.

Every job in ``ci.yml`` blocks on ``failure`` / ``cancelled``. The former
``score`` advisory exception left with the score tooling (#4868) — review
skills are the sole quality gate.

``skipped`` is tolerated everywhere *except* on the lanes in
``ALWAYS_EVALUATED_ON_PUSH`` (DIG-2305). Tolerating it is why this aggregator exists —
no path-gated job can be named in develop's branch protection, so a PR that misses a lane
reports no status for that lane's name at all and GitHub would block forever. But the same
tolerance let a lane that *never runs on develop at all* pass: on develop head `e45b12e7`,
``npm-audit`` was ``skipped`` and this job reported ``success``. A lane reported as passing
that evaluated nothing is a false negative, so on a push those jobs must have a real verdict.
"""

from __future__ import annotations

import json
import os
import sys

# No advisory exceptions: every job under ``required-checks.needs`` in
# ``.github/workflows/ci.yml`` blocks the merge gate. (The ``score`` advisory
# set left with the score tooling in #4868.)
ADVISORY_JOBS: frozenset[str] = frozenset()

# Jobs whose `if:` in ci.yml must evaluate on every push to develop/main, so a push can
# never report them as `skipped`. `npm-audit` is here because the advisory set is a
# property of *time* while its path filter answers a property of the *diff*: the five
# `next` advisories of 2026-10-07 had nowhere to land on develop, so they surfaced on
# PR #5107 — a PR whose lockfile was strictly better than develop's — and cost a full
# round of auditing develop to disprove as the cause. See
# tests/scripts/test_ci_npm_audit_evaluates_on_push.py.
ALWAYS_EVALUATED_ON_PUSH: frozenset[str] = frozenset({"npm-audit"})


def classify_needs(
    results: dict[str, dict[str, object]],
    *,
    advisory: frozenset[str] = ADVISORY_JOBS,
    require_evaluated: bool = False,
    always_evaluated: frozenset[str] = ALWAYS_EVALUATED_ON_PUSH,
) -> tuple[dict[str, str], dict[str, str]]:
    """Split needs into (blocking_failures, advisory_failures).

    A job is a failure when its ``result`` is not ``success`` or ``skipped``.
    Advisory jobs are reported separately so the aggregator can warn without
    failing the merge gate.

    ``require_evaluated`` is the push-only tightening from DIG-2305: a job in
    ``always_evaluated`` that reported ``skipped`` is a blocking failure there,
    because a lane that did not run did not gate anything. It stays tolerated on
    ``pull_request``, where a doc-only PR legitimately skips it.
    """
    blocking: dict[str, str] = {}
    advisory_failed: dict[str, str] = {}
    for name, meta in results.items():
        result = str(meta.get("result", ""))
        if result == "skipped":
            if require_evaluated and name in always_evaluated:
                blocking[name] = "skipped (required to evaluate on a push)"
            continue
        if result == "success":
            continue
        if name in advisory:
            advisory_failed[name] = result
        else:
            blocking[name] = result
    return blocking, advisory_failed


def _pushed() -> bool:
    """True when this run is a branch push, where `skipped` is not tolerated.

    Reads the ``PUSH_EVENT`` env var rather than ``GITHUB_EVENT_NAME`` so the
    condition is settable from a test and from the workflow alike. GitHub's own
    boolean-to-string rendering is ``true``/``false``; anything unrecognised is
    treated as "not a push", so a missing or mangled variable fails closed in the
    permissive direction this script has always had for PRs.
    """
    return os.environ.get("PUSH_EVENT", "").strip().lower() == "true"


def main(argv: list[str] | None = None) -> int:
    del argv  # CLI takes RESULTS from the environment only.
    raw = os.environ.get("RESULTS")
    if raw is None:
        print("RESULTS env var is required (JSON object of needs.*)", file=sys.stderr)
        return 2
    results = json.loads(raw)
    if not isinstance(results, dict):
        print("RESULTS must be a JSON object", file=sys.stderr)
        return 2

    blocking, advisory_failed = classify_needs(results, require_evaluated=_pushed())
    summary = {k: str(v.get("result", "")) for k, v in results.items()}
    if advisory_failed:
        print("Advisory (non-blocking) jobs failed:", advisory_failed)
    if blocking:
        print("Failed or cancelled required jobs:", blocking)
        return 1
    print("All required jobs passed or were skipped:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
