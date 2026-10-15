"""Rendering for the preflight and health output (plan section 6: JSON + table).

The table is for a human at a terminal; the JSON is what CI and the tests read.
Both are produced from the same objects so they cannot disagree.
"""

from __future__ import annotations

import json
from collections.abc import Iterable, Mapping, Sequence
from typing import Any

from .contracts import Check, resolve
from .health import GateReport, Result
from .orchestrate import StepReport, step_rows
from .preflight import PreflightReport

STATUS_MARK = {
    "passed": "PASS",
    "failed": "FAIL",
    "skipped": "SKIP",
}


def render_table(headers: Sequence[str], rows: Iterable[Sequence[str]]) -> str:
    """Fixed-width table. Widths come from the data, not from a guess."""
    materialised = [[str(c) for c in row] for row in rows]
    all_rows = [list(headers), *materialised]
    widths = [max(len(row[i]) for row in all_rows) for i in range(len(headers))]
    out = ["  ".join(h.ljust(widths[i]) for i, h in enumerate(headers)).rstrip()]
    for row in materialised:
        out.append("  ".join(c.ljust(widths[i]) for i, c in enumerate(row)).rstrip())
    return "\n".join(out)


def gate_rows(report: GateReport) -> list[list[str]]:
    return [
        [r.name, STATUS_MARK.get(r.status, r.status), f"{r.elapsed_ms} ms", r.detail]
        for r in report.results
    ]


def render_gate_table(report: GateReport) -> str:
    counts = report.to_dict()["counts"]
    assert isinstance(counts, dict)
    header = (
        f"profile={report.profile}  catalogue={report.origin}  "
        f"passed={counts['passed']} failed={counts['failed']} skipped={counts['skipped']}"
    )
    body = render_table(["CHECK", "STATE", "TIME", "DETAIL"], gate_rows(report))
    verdict = "GATE PASSED" if report.ok else "GATE FAILED"
    if report.require_all and report.skipped and not report.failed:
        verdict = "GATE FAILED (--require-all: skipped checks are failures)"
    return f"{header}\n{body}\n{verdict}"


def gate_json(report: GateReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def render_preflight_table(report: PreflightReport) -> str:
    rows = [[r.name, "OK" if r.ok else "MISSING", r.detail] for r in report.results]
    body = render_table(["CHECK", "STATE", "DETAIL"], rows)
    verdict = "PREFLIGHT OK" if report.ok else "PREFLIGHT FAILED: " + ", ".join(report.missing)
    return f"{body}\n{verdict}"


def preflight_json(report: PreflightReport) -> str:
    return json.dumps(report.to_dict(), indent=2, sort_keys=True)


def results_json(results: Sequence[Result]) -> str:
    payload: list[dict[str, Any]] = [r.to_dict() for r in results]
    return json.dumps(payload, indent=2, sort_keys=True)


def render_url_table(checks: Sequence[Check], config: Mapping[str, str], profile: str) -> str:
    """The URL table the plan's bring-up is required to print.

    Shows a check as reachable only when it actually resolved a URL.  An
    unconfigured surface is printed as ``(not configured)`` with the variable
    that would configure it, because printing a plausible URL nobody can reach
    is worse than printing nothing.
    """
    rows: list[tuple[str, ...]] = []
    for check in checks:
        if not check.in_profile(profile):
            continue
        url, reason = resolve(check, config)
        rows.append(
            (
                check.name,
                "http" if check.kind == "http" else check.kind,
                url or f"(not configured: {reason})",
                check.source,
            )
        )
    table = render_table(("SERVICE", "KIND", "URL", "SOURCE"), rows)
    return "\n".join(
        [
            f"URL table (profile {profile}) - every row's URL is sourced; "
            f"rows marked (not configured) are not reachable",
            table,
        ]
    )


def render_step_table(report: StepReport) -> str:
    """Console table for an orchestration plan."""
    table = render_table(("STEP", "STATE", "DETAIL"), step_rows(report))
    verb = "dry run" if report.dry_run else "plan"
    if report.ok:
        return "\n".join([f"{verb} {report.command}: OK", table])
    failed = ", ".join(o.name for o in report.failed)
    return "\n".join([f"{verb} {report.command}: FAILED ({failed})", table])
