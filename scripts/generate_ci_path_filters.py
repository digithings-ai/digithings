#!/usr/bin/env python3
"""Generate dorny/paths-filter block for ci.yml from scripts/ci_paths.yaml."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

import yaml

REPO_ROOT = Path(__file__).resolve().parent.parent
SOURCE = REPO_ROOT / "scripts" / "ci_paths.yaml"
CI_YML = REPO_ROOT / ".github" / "workflows" / "ci.yml"
START = "# CI_PATH_FILTERS_START — generated from scripts/ci_paths.yaml"
END = "# CI_PATH_FILTERS_END"


def render_filters(data: dict[str, list[str]]) -> str:
    lines: list[str] = []
    for name, paths in data.items():
        lines.append(f"            {name}:")
        for path in paths:
            lines.append(f"              - '{path}'")
    return "\n".join(lines) + "\n"


def load_filters() -> dict[str, list[str]]:
    raw = yaml.safe_load(SOURCE.read_text(encoding="utf-8"))
    if not isinstance(raw, dict):
        raise SystemExit(f"{SOURCE}: expected mapping at root")
    return {str(k): [str(p) for p in v] for k, v in raw.items()}


def patch_ci_yml(filters_block: str) -> str:
    text = CI_YML.read_text(encoding="utf-8")
    if START not in text or END not in text:
        raise SystemExit(f"{CI_YML}: missing {START!r} / {END!r} markers")
    before, rest = text.split(START, 1)
    _, after = rest.split(END, 1)
    return before + START + "\n" + filters_block + "            " + END + after


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--check",
        action="store_true",
        help="Exit 1 if ci.yml embedded block drifts from ci_paths.yaml",
    )
    parser.add_argument("--print", action="store_true", help="Print filters block only")
    args = parser.parse_args()

    filters_block = render_filters(load_filters())

    if args.print:
        print(filters_block, end="")
        return 0

    expected = patch_ci_yml(filters_block)
    current = CI_YML.read_text(encoding="utf-8")

    if args.check:
        if current != expected:
            print(
                "ci.yml path filters drift from scripts/ci_paths.yaml — "
                "run: python3 scripts/generate_ci_path_filters.py",
                file=sys.stderr,
            )
            return 1
        print("ci path filters OK")
        return 0

    CI_YML.write_text(expected, encoding="utf-8")
    print(f"updated {CI_YML.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
