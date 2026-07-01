#!/usr/bin/env python3
"""Infer a project_fields.tsv row from GitHub issue labels."""

from __future__ import annotations

import json
import sys


def infer_row(issue_number: int, labels: list[dict[str, str]]) -> tuple[str, str, str, str, str, str]:
    names = {label["name"] for label in labels}

    phase = "Phase 3 — Domain unification"
    if "phase-0" in names or "phase-2" in names:
        phase = "Phase 2 — Hardening"
    elif "phase-3" in names:
        phase = "Phase 3 — Domain unification"
    elif "phase-4" in names:
        phase = "Phase 4 — Atlas on DigiGraph"
    elif "phase-5" in names:
        phase = "Phase 5 — Atlas tiering"
    elif "sitaas" in names:
        phase = "SITAAS pilot"

    area = "Cross-cutting"
    component_map = {
        "component:website": "Website",
        "component:digichat": "DigiChat",
        "component:digisearch": "DigiSearch",
        "component:digigraph": "DigiGraph",
        "component:digiquant": "DigiQuant",
        "component:digikey": "DigiKey",
        "component:digismith": "DigiSmith",
    }
    for label, board_area in component_map.items():
        if label in names:
            area = board_area
            break
    if "sitaas" in names:
        area = "SITAAS"

    kind = "Task"
    if "epic" in names:
        kind = "Epic"
    elif "phase-0" in names:
        kind = "Feature"

    priority = "P1" if ("epic" in names or "phase-0" in names) else "P2"
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
