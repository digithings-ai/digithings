#!/usr/bin/env python3
"""Classify CI ``needs`` results for the ``required-checks`` aggregator job.

``score`` is an optional rubric (AGENTS.md / docs/scoring) — it still runs and
can exit non-zero, but must not take down the develop merge gate. Every other
job in ``ci.yml`` remains blocking on ``failure`` / ``cancelled``.
"""

from __future__ import annotations

import json
import os
import sys

# Job ids as listed under ``required-checks.needs`` in ``.github/workflows/ci.yml``.
ADVISORY_JOBS: frozenset[str] = frozenset({"score"})


def classify_needs(
    results: dict[str, dict[str, object]],
    *,
    advisory: frozenset[str] = ADVISORY_JOBS,
) -> tuple[dict[str, str], dict[str, str]]:
    """Split needs into (blocking_failures, advisory_failures).

    A job is a failure when its ``result`` is not ``success`` or ``skipped``.
    Advisory jobs are reported separately so the aggregator can warn without
    failing the merge gate.
    """
    blocking: dict[str, str] = {}
    advisory_failed: dict[str, str] = {}
    for name, meta in results.items():
        result = str(meta.get("result", ""))
        if result in ("success", "skipped"):
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
        return 1
    print("All required jobs passed or were skipped:", summary)
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
