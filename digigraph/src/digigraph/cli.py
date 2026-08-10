"""``digi`` command-line interface.

Phase 1 surface: ``digi project validate``, ``digi project migrate``, and
``digi llm-settings`` (read/print effective LLM resolution — never prints secrets).
"""

from __future__ import annotations

import argparse
import json
import os
import sys
from typing import Sequence

from digigraph.project_migrate import migrate_project_file
from digigraph.project_validate import validate_project_file


def _build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        prog="digi",
        description="digithings CLI.",
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

    llm = sub.add_parser(
        "llm-settings",
        help="Print effective LLM provider/model/key-env (never prints secrets).",
    )
    llm.add_argument(
        "--config",
        default=None,
        help="Path to digiproject.yaml (sets DIGI_PROJECT_CONFIG for this run).",
    )
    llm.add_argument(
        "--json",
        action="store_true",
        help="Emit JSON instead of key: value lines.",
    )

    return parser


def _cmd_llm_settings(*, config: str | None, as_json: bool) -> int:
    """Print effective LLM settings; never include secret values."""
    if config:
        os.environ["DIGI_PROJECT_CONFIG"] = config
    from digigraph.model_config import effective_llm_settings

    settings = effective_llm_settings()
    # Defense: never leak env values even if a future helper adds them.
    safe = {
        k: v
        for k, v in settings.items()
        if k
        not in (
            "api_key",
            "key",
            "secret",
            "token",
        )
    }
    if as_json:
        print(json.dumps(safe, indent=2, sort_keys=True))
    else:
        for key in (
            "llm_mode",
            "provider",
            "model",
            "api_key_env",
            "api_key_present",
            "source",
        ):
            if key in safe:
                print(f"{key}: {safe[key]}")
    return 0


def main(argv: Sequence[str] | None = None) -> int:
    """CLI entry point. Returns the process exit code (0 = ok, 1 = error)."""
    parser = _build_parser()
    args = parser.parse_args(argv)

    if args.group == "llm-settings":
        return _cmd_llm_settings(config=args.config, as_json=args.json)

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

    parser.error(f"unknown command: {args.group} {getattr(args, 'command', '')}")
    return 2  # unreachable — argparse.error exits


if __name__ == "__main__":  # pragma: no cover
    sys.exit(main())
