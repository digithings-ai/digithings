#!/usr/bin/env python3
"""Compare-harness stub for digithings dogfood Stage 8.

Prints the canonical question checklist from
``docs/projects/digithings/GAPLOG.md`` and optionally posts probe queries when
``DIGISEARCH_URL`` / vault credentials are available.

Without secrets this is a documentation-oriented dry checklist::

    python scripts/dogfood_compare_harness.py --dry-run
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path

CANONICAL = [
    "What does digigraph orchestrate?",
    "How do I install self-hosted digichat (Profile A)?",
    "Where is digiquant's OpenAPI / run_backtest surface?",
    "Summarize a recent ADR relevant to digichat embed CSP",
    "What does digivault search when DIGIVAULT_ROOT is unset?",
    "digiquant.io marketing: what is the product pitch?",
    "How does docs_onboard dual-sink work?",
    "What scopes does digikey issue for digivault writes?",
    "Where do AGENTS.md non-negotiables live?",
    "Auth on digithings.ai/chat — login wall or ungated embed?",
]


def main(argv: list[str] | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--dry-run", action="store_true", default=True)
    ap.add_argument(
        "--gaplog",
        type=Path,
        default=Path("docs/projects/digithings/GAPLOG.md"),
    )
    args = ap.parse_args(argv)
    rows = [
        {"n": i + 1, "question": q, "hit": None, "citation": None} for i, q in enumerate(CANONICAL)
    ]
    print(json.dumps({"gaplog": str(args.gaplog), "questions": rows}, indent=2))
    print(
        "\nRecord answers in docs/projects/digithings/GAPLOG.md after live chat probes.",
        file=sys.stderr,
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
