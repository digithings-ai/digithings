#!/usr/bin/env python3
"""Merge config/litellm.cheaperinference.yaml over config/litellm.yaml.

Replaces matching ``model_name`` entries so house OpenRouter-style slugs that
exist on Cheaper Inference route there; everything else (sonar, :online,
maverick, grok-4.3/4.6, anthropic, Ollama, …) stays on the default file.

Usage:
  python scripts/merge_litellm_cheaperinference.py > /tmp/litellm.merged.yaml
  LITELLM_CONFIG=/tmp/litellm.merged.yaml  # compose / litellm --config

Does not call any paid API. Requires PyYAML.
"""

from __future__ import annotations

import argparse
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
    args = parser.parse_args(argv)
    merged = merge(args.base, args.overlay)
    text = yaml.safe_dump(merged, sort_keys=False, default_flow_style=False)
    if args.output is None:
        sys.stdout.write(text)
    else:
        args.output.write_text(text, encoding="utf-8")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
