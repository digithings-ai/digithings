#!/usr/bin/env python3
"""Infer a project_fields.tsv row from GitHub issue labels."""

from __future__ import annotations

import json
import sys


def infer_row(issue_number: int, labels: list[dict[str, str]]) -> tuple[str, str, str, str, str, str]:
    names = {label["name"] for label in labels}

    # Board cleanup 2026-09: phase-0..phase-5 labels deleted (phase now lives
    # on the milestone, which this script doesn't see). Default + human
    # verification on the stub PR (its body says "verify before merging").
    phase = "Phase 3 — Domain unification"
    if "client-pilot" in names:
        phase = "Client Pilot"

    area = "Cross-cutting"
    component_map = {
        "component:website": "Website",
        "component:digichat": "digichat",
        "component:digisearch": "digisearch",
        "component:digigraph": "digigraph",
        "component:digiquant": "digiquant",
        "component:digikey": "digikey",
        "component:digismith": "digismith",
    }
    for label, board_area in component_map.items():
        if label in names:
            area = board_area
            break
    if "client-pilot" in names:
        area = "Client Pilot"

    kind = "Task"
    if "epic" in names:
        kind = "Epic"

    priority = "P1" if "epic" in names else "P2"
    model = "opus" if "risk:high" in names else "sonnet"

    return (
        str(issue_number),
        phase,
        area,
        kind,
        priority,
        model,
    )


def main() -> int:
    if len(sys.argv) != 3:
        print("usage: infer_project_fields_row.py <issue_number> <labels_json>", file=sys.stderr)
        return 2
    issue_number = int(sys.argv[1])
    labels = json.loads(sys.argv[2])
    row = infer_row(issue_number, labels)
    print("\t".join(row))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
