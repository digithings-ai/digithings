#!/usr/bin/env python3
"""Classify CI ``needs`` results for the ``required-checks`` aggregator job.

Every job in ``ci.yml`` blocks on ``failure`` / ``cancelled``. The former
``score`` advisory exception left with the score tooling (#4868) — review
skills are the sole quality gate.

``skipped`` is tolerated for a *path-gated* job: outside its filter the diff
has nothing to say about it, and reporting that as a pass is what lets one
stable required-check name exist at all. It is **not** tolerated for the jobs
in ``MUST_RUN_JOBS`` (#2371). Those carry no ``if:`` gate, so nothing can skip
them; a ``skipped`` result there means the lane never ran, and reporting
success for a check nobody performed is a false green.
"""

from __future__ import annotations

import json
import os
import sys

# No advisory exceptions: every job under ``required-checks.needs`` in
# ``.github/workflows/ci.yml`` blocks the merge gate. (The ``score`` advisory
# set left with the score tooling in #4868.)
ADVISORY_JOBS: frozenset[str] = frozenset()

# Jobs in ``ci.yml`` that carry no ``if:`` gate, so no path filter can skip
# them. Their verdict is a property of the committed tree, not of the diff:
# ``changes`` classifies the diff, ``frontend-canon`` and ``npm-audit`` read
# files the diff may never mention (#1404, #2371). A ``skipped`` result for one
# of these is a "did not run", not a "not applicable", so it blocks.
# ``required-checks`` is deliberately absent: the aggregator gates itself on
# ``always()`` because it has to outlive a cancelled dependency.
# Tests mirror this set off ci.yml (``MUST_RUN_JOBS_MATCHES_UNGATED_JOBS``), so
# re-gating one of these jobs without updating the set fails the suite loudly.
MUST_RUN_JOBS: frozenset[str] = frozenset({"changes", "frontend-canon", "npm-audit"})


def classify_needs(
    results: dict[str, dict[str, object]],
    *,
    advisory: frozenset[str] = ADVISORY_JOBS,
    must_run: frozenset[str] = MUST_RUN_JOBS,
) -> tuple[dict[str, str], dict[str, str]]:
    """Split needs into (blocking_failures, advisory_failures).

    A job is a failure when its ``result`` is not ``success``, and also when it
    is ``skipped`` and not path-gated — see ``MUST_RUN_JOBS`` (#2371).
    Advisory jobs are reported separately so the aggregator can warn without
    failing the merge gate.
    """
    blocking: dict[str, str] = {}
    advisory_failed: dict[str, str] = {}
    for name, meta in results.items():
        result = str(meta.get("result", ""))
        if result == "success":
            continue
        if result == "skipped" and name not in must_run:
            continue
        if name in advisory:
            advisory_failed[name] = result
        else:
            blocking[name] = result
    return blocking, advisory_failed


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

    blocking, advisory_failed = classify_needs(results)
    summary = {k: str(v.get("result", "")) for k, v in results.items()}
    if advisory_failed:
        print("Advisory (non-blocking) jobs failed:", advisory_failed)
    if blocking:
        print("Failed or cancelled required jobs:", blocking)
        did_not_run = sorted(name for name, result in blocking.items() if result == "skipped")
        if did_not_run:
            print(
                "Required jobs that carry no `if:` gate did not run:",
                did_not_run,
            )
            for name in did_not_run:
                print(
                    f"::error::{name} is required on every push and was skipped, so its"
                    " check never ran — a skip is not a pass for a job nothing could"
                    " legitimately skip."
                )
        return 1
    print(
        "All required jobs passed or were skipped (skips are tolerated only for"
        " path-gated jobs; the ungated ones must pass):",
        summary,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
