#!/usr/bin/env python3
"""WP10.5 — file-only paired allocation shadow comparison CLI (#2799).

Loads a frozen criteria version first, then two arm request/result JSON pairs,
and writes an immutable comparison report. Never contacts production I/O,
brokers, or H8/H9 booking paths.
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

from digiquant.olympus.replay.allocation_comparison import (
    ComparisonArm,
    ComparisonArmInput,
    compare_allocation_arms,
    load_shadow_criteria,
    write_comparison_report,
)
from digiquant.olympus.replay.models import PortfolioReplayRequest, PortfolioReplayResult


def _load_json(path: Path) -> object:
    return json.loads(path.read_text(encoding="utf-8"))


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Compare incumbent vs challenger portfolio replay arms (shadow evidence only)."
    )
    parser.add_argument(
        "--criteria",
        type=Path,
        default=None,
        help="Versioned shadow criteria JSON (default: packaged v1).",
    )
    parser.add_argument(
        "--incumbent-request",
        type=Path,
        required=True,
        help="Incumbent PortfolioReplayRequest JSON.",
    )
    parser.add_argument(
        "--incumbent-result",
        type=Path,
        required=True,
        help="Incumbent PortfolioReplayResult JSON.",
    )
    parser.add_argument(
        "--challenger-request",
        type=Path,
        required=True,
        help="Challenger PortfolioReplayRequest JSON.",
    )
    parser.add_argument(
        "--challenger-result",
        type=Path,
        required=True,
        help="Challenger PortfolioReplayResult JSON.",
    )
    parser.add_argument(
        "--incumbent-weights-fingerprint",
        required=True,
        help="Incumbent book weights fingerprint.",
    )
    parser.add_argument(
        "--challenger-weights-fingerprint",
        required=True,
        help="Challenger book weights fingerprint.",
    )
    parser.add_argument(
        "--challenger-breach",
        action="append",
        default=[],
        help="Hard-constraint breach id on challenger (repeatable).",
    )
    parser.add_argument(
        "--artifact-content-hash",
        default=None,
        help="Optional upstream ShadowAllocationArtifact content hash.",
    )
    parser.add_argument(
        "--output",
        type=Path,
        required=True,
        help="File-only output path for AllocationComparisonReport JSON.",
    )
    args = parser.parse_args(argv)

    # Freeze criteria before inspecting arm results (WP10.5 / Gate 3).
    criteria = load_shadow_criteria(args.criteria)

    incumbent_req = PortfolioReplayRequest.model_validate(_load_json(args.incumbent_request))
    incumbent_res = PortfolioReplayResult.model_validate(_load_json(args.incumbent_result))
    challenger_req = PortfolioReplayRequest.model_validate(_load_json(args.challenger_request))
    challenger_res = PortfolioReplayResult.model_validate(_load_json(args.challenger_result))

    report = compare_allocation_arms(
        criteria=criteria,
        incumbent=ComparisonArmInput(
            arm=ComparisonArm.INCUMBENT,
            weights_fingerprint=args.incumbent_weights_fingerprint,
            request=incumbent_req,
            result=incumbent_res,
        ),
        challenger=ComparisonArmInput(
            arm=ComparisonArm.CHALLENGER,
            weights_fingerprint=args.challenger_weights_fingerprint,
            request=challenger_req,
            result=challenger_res,
            hard_constraint_breaches=tuple(args.challenger_breach),
        ),
        artifact_content_hash=args.artifact_content_hash,
    )
    write_comparison_report(report, args.output)
    print(
        json.dumps(
            {
                "status": report.status.value,
                "report_content_hash": report.report_content_hash,
                "criteria_version": report.criteria_version,
                "output": str(args.output),
            },
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    sys.exit(main())
