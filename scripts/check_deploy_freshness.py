#!/usr/bin/env python3
"""Evaluate a live site's deploy build stamp and fail when the deploy is frozen (#1759).

Why this exists
---------------
digiquant.io is a Cloudflare Pages static export. Every existing smoke probe in
``smoke-site.yml`` asks *does the URL answer with the right content type* — a
question a frozen deploy answers perfectly, forever. Pages keeps serving the
last successful build with a 200 and no ``last-modified`` header (verified
2026-08-01), so a project that has stopped producing deployments is
indistinguishable from a healthy one from the outside.

``scripts/write-build-info.sh`` writes ``build-info.json`` into the export root
at build time; this script reads it back off the live site and turns "when was
this bundle built" into a pass/fail verdict.

Deliberately *not* in scope: why a given Pages project stopped building. That is
answerable only in the Cloudflare dashboard (deployment list, build logs,
production branch, watch paths, environment variables). This script detects the
symptom; it does not diagnose the cause.

Verdict vocabulary mirrors the existing ``probe()`` shell function in
``smoke-site.yml``, where a warning is reserved for genuinely *inconclusive*
results (Cloudflare bot challenges from CI IPs) and everything conclusive is a
pass or a failure. A missing stamp is conclusive: the live bundle predates the
stamp, i.e. the deploy is older than the commit that added it.

Threshold
---------
``--max-age-hours`` defaults to 168 (7 days). The site only rebuilds when
Cloudflare Pages observes a push to its production branch, and the repository
can legitimately go several quiet days without a frontend-touching commit. A
window under ~72h would cry wolf over a long weekend; 7 days is well inside the
time it took for the current freeze to be noticed.

Usage (see ``.github/workflows/smoke-site.yml``)::

    curl -sL -o body.json -w '%{http_code}' https://digiquant.io/build-info.json
    python3 scripts/check_deploy_freshness.py \
        --url https://digiquant.io/build-info.json \
        --status "$status" --body-file body.json --max-age-hours 168

The HTTP fetch stays in ``curl`` so this stays a pure, offline-testable
evaluator that reuses the workflow's existing user agent and redirect handling
rather than introducing a second HTTP client with different semantics.
"""

from __future__ import annotations

import argparse
import json
import sys
from dataclasses import dataclass
from datetime import UTC, datetime
from pathlib import Path

#: HTTP statuses that mean "the answer came from Cloudflare's bot defences, not
#: from the origin" — same warn-only treatment the shell probes give them.
INCONCLUSIVE_STATUSES = frozenset({0, 403, 429})

#: A ranged/plain successful read of a static asset.
OK_STATUSES = frozenset({200, 206})

#: A stamp dated further ahead than this is a clock or template bug, not a
#: fresh deploy — refuse to let a bogus future date mask a frozen site.
MAX_FUTURE_SKEW_HOURS = 24.0

DEFAULT_MAX_AGE_HOURS = 168.0


@dataclass(frozen=True)
class Verdict:
    """One evaluated probe result. ``failed`` drives the process exit code."""

    label: str
    message: str
    failed: bool


def _parse_built_at(raw: str) -> datetime | None:
    """Parse the stamp's ``built_at`` as an aware UTC datetime, or ``None``."""
    text = raw.strip()
    if not text:
        return None
    # ``write-build-info.sh`` emits a trailing "Z"; accept the explicit-offset
    # spelling too so a hand-edited or future stamp writer still parses.
    if text.endswith(("z", "Z")):
        text = f"{text[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(text)
    except ValueError:
        return None
    return parsed.replace(tzinfo=UTC) if parsed.tzinfo is None else parsed.astimezone(UTC)


def evaluate(
    *,
    url: str,
    status: int,
    body: str,
    now: datetime,
    max_age_hours: float = DEFAULT_MAX_AGE_HOURS,
) -> Verdict:
    """Turn an HTTP status plus response body into a freshness verdict.

    Pure and offline: every branch is unit-tested in
    ``tests/scripts/test_check_deploy_freshness.py``.
    """
    if status in INCONCLUSIVE_STATUSES:
        return Verdict(
            "WARN",
            f"{url} -> HTTP {status} (bot challenge or no response; inconclusive from CI)",
            failed=False,
        )

    if status == 404:
        return Verdict(
            "UNSTAMPED",
            f"{url} -> HTTP 404: the live deploy predates the build stamp, so it is "
            "older than the commit that added build-info.json (see #1759)",
            failed=True,
        )

    if status not in OK_STATUSES:
        return Verdict("UNREACHABLE", f"{url} -> HTTP {status}", failed=True)

    try:
        payload = json.loads(body)
    except ValueError:
        # A Pages SPA fallback answers an unknown path with 200 text/html, which
        # is the same shape as "this deploy has no stamp".
        return Verdict(
            "UNSTAMPED",
            f"{url} -> HTTP {status} but the body is not JSON: the live deploy has no "
            "build stamp (SPA fallback), so it predates build-info.json (see #1759)",
            failed=True,
        )
    if not isinstance(payload, dict):
        return Verdict(
            "MALFORMED", f"{url} -> JSON body is not an object: {body[:120]!r}", failed=True
        )

    raw_built_at = payload.get("built_at")
    built_at = _parse_built_at(raw_built_at) if isinstance(raw_built_at, str) else None
    if built_at is None:
        return Verdict(
            "MALFORMED",
            f"{url} -> stamp has no parseable 'built_at' (got {raw_built_at!r})",
            failed=True,
        )

    identity = " ".join(
        f"{field}={payload.get(field)!s}"
        for field in ("site", "branch", "commit", "builder")
        if payload.get(field)
    )
    age_hours = (now - built_at).total_seconds() / 3600.0
    detail = f"built_at={built_at:%Y-%m-%dT%H:%M:%SZ} age={age_hours / 24:.1f}d {identity}".rstrip()

    if age_hours < -MAX_FUTURE_SKEW_HOURS:
        return Verdict(
            "MALFORMED",
            f"{url} -> stamp is dated {-age_hours / 24:.1f}d in the future; {detail}",
            failed=True,
        )
    if age_hours > max_age_hours:
        return Verdict(
            "STALE",
            f"{url} -> no deploy for {age_hours / 24:.1f}d "
            f"(limit {max_age_hours / 24:.1f}d); {detail}",
            failed=True,
        )
    return Verdict("PASS", f"{url} -> {detail}", failed=False)


def _read_body(path: Path | None) -> str:
    """Read the curl output file, tolerating the file curl never created."""
    if path is None:
        return ""
    try:
        return path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return ""


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawTextHelpFormatter
    )
    parser.add_argument("--url", required=True, help="URL the stamp was fetched from (label only)")
    parser.add_argument("--status", required=True, help="HTTP status from curl's %%{http_code}")
    parser.add_argument("--body-file", type=Path, help="File curl wrote the response body to")
    parser.add_argument(
        "--max-age-hours",
        type=float,
        default=DEFAULT_MAX_AGE_HOURS,
        help=f"Fail when the stamp is older than this (default {DEFAULT_MAX_AGE_HOURS:g})",
    )
    args = parser.parse_args(argv)

    try:
        # curl writes literal "000" when it never got a response.
        status = int(args.status.strip() or 0)
    except ValueError:
        status = 0

    verdict = evaluate(
        url=args.url,
        status=status,
        body=_read_body(args.body_file),
        now=datetime.now(tz=UTC),
        max_age_hours=args.max_age_hours,
    )
    stream = sys.stderr if verdict.failed else sys.stdout
    print(f"{verdict.label}  {verdict.message}", file=stream)
    return 1 if verdict.failed else 0


if __name__ == "__main__":  # pragma: no cover - CLI entry point
    sys.exit(main())
