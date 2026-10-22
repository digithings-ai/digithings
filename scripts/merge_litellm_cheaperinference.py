#!/usr/bin/env python3
"""Merge config/litellm.cheaperinference.yaml over config/litellm.yaml.

Replaces matching ``model_name`` entries so house OpenRouter-style slugs that
exist on Cheaper Inference route there; everything else (sonar, :online,
unmapped / retired OpenRouter orphans, Ollama, …) stay on the default file or were removed in #3788.

Usage:
  python scripts/merge_litellm_cheaperinference.py > /tmp/litellm.merged.yaml
  LITELLM_CONFIG=/tmp/litellm.merged.yaml  # compose / litellm --config

Container boot (DIG-4512) adds --require-curated-ids: the merged model_list
must carry every curated house model (DIGI_SESSION_MODEL_ALLOWLIST) or the
merge fails with the missing ids named and no config file is written. The
base file the image ships has no curated model, so serving it silently answers
every curated tenant model with model-not-found while /health stays green.

Does not call any paid API. Requires PyYAML.
"""

from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

try:
    import yaml
except ImportError as exc:  # pragma: no cover
    raise SystemExit("PyYAML required: pip install pyyaml") from exc

REPO = Path(__file__).resolve().parents[1]
DEFAULT_BASE = REPO / "config" / "litellm.yaml"
DEFAULT_OVERLAY = REPO / "config" / "litellm.cheaperinference.yaml"


def _load(path: Path) -> dict:
    if not path.is_file():
        raise SystemExit(f"{path} not found")
    data = yaml.safe_load(path.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise SystemExit(f"{path} must parse as a mapping")
    return data


def merge(base_path: Path, overlay_path: Path) -> dict:
    base = _load(base_path)
    overlay = _load(overlay_path)
    base_list = base.get("model_list")
    overlay_list = overlay.get("model_list")
    if not isinstance(base_list, list) or not isinstance(overlay_list, list):
        raise SystemExit("both configs need a model_list")
    by_name = {
        entry["model_name"]: entry
        for entry in overlay_list
        if isinstance(entry, dict) and isinstance(entry.get("model_name"), str)
    }
    merged: list = []
    seen: set[str] = set()
    for entry in base_list:
        if not isinstance(entry, dict):
            merged.append(entry)
            continue
        name = entry.get("model_name")
        if isinstance(name, str) and name in by_name:
            merged.append(by_name[name])
            seen.add(name)
        else:
            merged.append(entry)
    for name, entry in by_name.items():
        if name not in seen:
            merged.append(entry)
    out = dict(base)
    out["model_list"] = merged
    return out


def curated_ids(allowlist: str) -> list[str]:
    """The curated model ids from a comma-separated list."""
    return [part.strip() for part in allowlist.split(",") if part.strip()]


def missing_curated_ids(merged: dict, allowlist: str) -> list[str]:
    """The curated ids the merged model_list does not carry."""
    names = {
        entry["model_name"]
        for entry in merged.get("model_list", [])
        if isinstance(entry, dict) and isinstance(entry.get("model_name"), str)
    }
    return [cid for cid in curated_ids(allowlist) if cid not in names]


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--base", type=Path, default=DEFAULT_BASE)
    parser.add_argument("--overlay", type=Path, default=DEFAULT_OVERLAY)
    parser.add_argument(
        "-o",
        "--output",
        type=Path,
        default=None,
        help="Write merged YAML here (default: stdout)",
    )
    parser.add_argument(
        "--allowlist",
        default=os.environ.get("DIGI_SESSION_MODEL_ALLOWLIST", ""),
        help=(
            "Comma-separated curated model ids that must survive the merge "
            "(default: $DIGI_SESSION_MODEL_ALLOWLIST)."
        ),
    )
    parser.add_argument(
        "--require-curated-ids",
        action="store_true",
        help=(
            "Fail when the merged model_list is missing a curated id. The missing "
            "ids are named on stderr and no config file is written."
        ),
    )
    parser.add_argument(
        "--check-config",
        type=Path,
        default=None,
        help=(
            "Check a single LiteLLM config for the curated house models. Exit 0 "
            "when it carries them all, 1 when it is missing some (the missing "
            "ids are printed on stdout), 2 when the check could not run. The "
            "boot path that serves the base config uses this, because the base "
            "file answers every curated tenant model with model-not-found while "
            "/health stays green (DIG-4512)."
        ),
    )
    args = parser.parse_args(argv)
    if args.check_config is not None:
        try:
            config = _load(args.check_config)
        except SystemExit as exc:
            print(
                f"ERROR: cheaperinference: cannot check {args.check_config}: {exc}",
                file=sys.stderr,
            )
            return 2
        missing = missing_curated_ids(config, args.allowlist)
        if missing:
            print(
                "ERROR: cheaperinference: the litellm model_list in "
                f"{args.check_config} is missing {len(missing)} curated model id(s): "
                + ", ".join(missing),
                file=sys.stderr,
            )
            print(",".join(missing))
            return 1
        return 0
    merged = merge(args.base, args.overlay)
    if args.require_curated_ids:
        missing = missing_curated_ids(merged, args.allowlist)
        if missing:
            print(
                "ERROR: cheaperinference: the merged litellm model_list is missing "
                f"{len(missing)} curated model id(s): " + ", ".join(missing),
                file=sys.stderr,
            )
            return 1
    text = yaml.safe_dump(merged, sort_keys=False, default_flow_style=False)
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
