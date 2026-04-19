"""``digi`` command-line interface.

Minimal surface for Phase 1: ``digi project validate <path>``. Additional subcommands
(``render``, ``migrate``) are tracked as separate backlog items.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from digigraph.project_validate import validate_project_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digi",
        description="DigiThings CLI.",
    )
    sub = parser.add_subparsers(dest="group", required=True)

    project = sub.add_parser("project", help="Project-level commands")
    project_sub = project.add_subparsers(dest="command", required=True)

    validate = project_sub.add_parser(
        "validate",
        help="Validate a digiproject.yaml file against the v1alpha1 schema.",
    )
    validate.add_argument("path", help="Path to the digiproject.yaml file.")

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code (0 = ok, 1 = validation error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.group == "project" and args.command == "validate":
        report = validate_project_file(args.path)
        print(f"{args.path}: {report.render()}")
        return 0 if report.ok else 1

    parser.error(f"unknown command: {args.group} {args.command}")
    return 2  # unreachable — argparse.error exits


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
