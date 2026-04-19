"""``digi`` command-line interface.

Phase 1 surface: ``digi project validate`` and ``digi project migrate``. The
``render`` subcommand is tracked as a separate backlog item.
"""

from __future__ import annotations

import argparse
import sys
from typing import Sequence

from digigraph.project_migrate import migrate_project_file
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

    migrate = project_sub.add_parser(
        "migrate",
        help="Migrate a pre-spec config.yaml to a v1alpha1 digiproject.yaml.",
    )
    migrate.add_argument("path", help="Path to the legacy config.yaml file.")
    migrate.add_argument(
        "-o",
        "--output",
        default=None,
        help="Destination path (default: digiproject.yaml next to the source).",
    )
    migrate.add_argument(
        "--force",
        action="store_true",
        help="Overwrite destination if it already exists.",
    )

    return parser


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code (0 = ok, 1 = error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.group == "project" and args.command == "validate":
        report = validate_project_file(args.path)
        print(f"{args.path}: {report.render()}")
        return 0 if report.ok else 1

    if args.group == "project" and args.command == "migrate":
        try:
            dest, mig_report, _val_report = migrate_project_file(
                args.path, args.output, force=args.force
            )
        except (FileNotFoundError, FileExistsError, ValueError) as exc:
            print(f"error: {exc}", file=sys.stderr)
            return 1
        print(f"{args.path} -> {dest}: {mig_report.render()}")
        return 0

    parser.error(f"unknown command: {args.group} {args.command}")
    return 2  # unreachable — argparse.error exits


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
