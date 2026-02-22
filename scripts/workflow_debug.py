#!/usr/bin/env python3
"""
Debug script: run research node in isolation to inspect strategy/symbols extraction.
Usage: PYTHONPATH=digiquant/src:digigraph/src:. python scripts/workflow_debug.py
"""

from __future__ import annotations

import json
import os
import sys

# Ensure PYTHONPATH includes digigraph
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "digigraph", "src"))
sys.path.insert(0, os.path.join(os.path.dirname(__file__), "..", "digiquant", "src"))

from digigraph.graph.nodes import research_node


def main() -> int:
    prompts = [
        "Build me a mean-reversion stat-arb on tech",
        "momentum on energy",
        "",
    ]
    for prompt in prompts:
        print(f"\n--- Prompt: {repr(prompt) or '(empty)'} ---")
        state = {"prompt": prompt, "session_id": "debug"}
        out = research_node(state)
        print(json.dumps(out, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
