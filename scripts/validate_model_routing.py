#!/usr/bin/env python3
"""Validate Atlas/Hermes model routing and provider connectivity.

Two modes:
  --routing   Print every phase slug → resolved model (no network calls).
  --ping      Fire a minimal 1-token completion against each distinct
              provider to confirm API keys + endpoints are reachable.
  (default)   Both.

Usage:
  python scripts/validate_model_routing.py
  python scripts/validate_model_routing.py --routing
  python scripts/validate_model_routing.py --ping
  DIGI_LLM_MODE=best python scripts/validate_model_routing.py
"""

from __future__ import annotations

import argparse
import os
import sys
import textwrap
from pathlib import Path

# ── path setup ──────────────────────────────────────────────────────────────
ROOT = Path(__file__).parent.parent

# ── Inline model-mode resolution (mirrors digigraph.llm logic) ───────────────
# Allows --routing to run without the digigraph package installed.


def _load_model_modes() -> dict:
    import yaml

    config_dir = os.environ.get("DIGI_CONFIG_PATH", str(ROOT / "config"))
    path = Path(config_dir) / "model_modes.yaml"
    with open(path) as f:
        return yaml.safe_load(f) or {}


def get_model_for_phase(slug: str) -> str | None:
    data = _load_model_modes()
    pm: dict = data.get("phase_models") or {}
    if slug in pm:
        return pm[slug]
    for key, mdl in pm.items():
        if key.endswith("-") and slug.startswith(key):
            return mdl
    return None


def get_model_for_mode() -> str:
    data = _load_model_modes()
    model = data.get("default_model")
    if model:
        return str(model)
    mode = os.environ.get("DIGI_LLM_MODE", "test").lower().strip()
    defaults = data.get("defaults") or {}
    return defaults.get(mode) or defaults.get("test") or "gpt-4o-mini"


# ── Phase slug inventory ─────────────────────────────────────────────────────
# All slugs that Atlas/Hermes phases pass to run_research_agent(phase_slug=…).
# Dynamic ones (per-ticker) are represented with a concrete example.

ALL_SLUGS: list[tuple[str, str]] = [
    # Phase 1 — alt-data extraction
    ("alt-sentiment-news", "Phase 1A — sentiment/news"),
    ("alt-cta-positioning", "Phase 1B — CTA positioning"),
    ("alt-options-derivatives", "Phase 1C — GEX/VIX/dealer"),
    ("alt-politician-signals", "Phase 1D — STOCK Act signals"),
    ("alt-ai-portfolios", "Phase 1E — AI-portfolio x_search"),
    # Phase 2 — institutional flows
    ("inst-institutional-flows", "Phase 2A — ETF flows / 13D-G"),
    ("inst-hedge-fund-intel", "Phase 2B — 13F / fund signals"),
    # Phase 3 — macro
    ("macro", "Phase 3 — macro regime"),
    # Phase 4 — asset classes
    ("bonds", "Phase 4A — fixed income"),
    ("commodities", "Phase 4B — commodities"),
    ("forex", "Phase 4C — FX"),
    ("crypto", "Phase 4D — crypto"),
    ("international", "Phase 4E — international"),
    # Phase 5 — equities
    ("equity", "Phase 5A — equity top-down"),
    ("sector-technology", "Phase 5B — technology"),
    ("sector-healthcare", "Phase 5C — healthcare"),
    ("sector-energy", "Phase 5D — energy"),
    ("sector-financials", "Phase 5E — financials"),
    ("sector-consumer-disc", "Phase 5F — consumer disc."),
    ("sector-consumer-staples", "Phase 5G — consumer staples"),
    ("sector-industrials", "Phase 5H — industrials"),
    ("sector-utilities", "Phase 5I — utilities"),
    ("sector-materials", "Phase 5J — materials"),
    ("sector-real-estate", "Phase 5K — real estate"),
    ("sector-comms", "Phase 5L — communications"),
    # Phase 7C — 4-axis analyst fan-out (prefix per axis)
    ("technical-analyst-AAPL", "Phase 7C — technical analyst (example ticker)"),
    ("sentiment-analyst-AAPL", "Phase 7C — sentiment analyst (example ticker)"),
    ("news-analyst-AAPL", "Phase 7C — news analyst (example ticker)"),
    ("fundamental-analyst-AAPL", "Phase 7C — fundamental analyst (example ticker)"),
    # Phase 7CD — bull/bear debate (prefix per role)
    ("bull-researcher-AAPL", "Phase 7CD — bull researcher"),
    ("bear-researcher-AAPL", "Phase 7CD — bear researcher"),
    ("research-manager-AAPL", "Phase 7CD — debate manager"),
    # Phase 7D — risk debate
    ("risk-aggressive", "Phase 7D — risk aggressive"),
    ("risk-conservative", "Phase 7D — risk conservative"),
    # Phase 7D — PM rebalance
    ("pm-rebalance", "Phase 7D — PM rebalance"),
    # Phase 7 — master digest synthesis
    ("master-digest", "Phase 7 — master digest synthesis"),
    # Phase monthly — explicit pin
    ("monthly-digest", "Phase monthly — month-end rollup"),
    # Phase 9 — explicit pin
    ("phase9-evolution", "Phase 9 — closed-loop evolution"),
    # Decision reflector (fall to defaults)
    ("decision-reflector", "Decision reflector"),
]


def _resolve(slug: str) -> str:
    return get_model_for_phase(slug) or get_model_for_mode()


def _provider(model: str) -> str:
    if model.startswith("gemini/"):
        return "gemini"
    if model.startswith("ollama-cloud/"):
        return "ollama-cloud"
    if model.startswith("openrouter/"):
        return "openrouter"
    return "default-openai"


# ── Routing table ─────────────────────────────────────────────────────────────


def print_routing_table() -> dict[str, list[str]]:
    mode = os.environ.get("DIGI_LLM_MODE", "test")
    print(f"\n{'=' * 70}")
    print(f"  Atlas/Hermes model routing table  (DIGI_LLM_MODE={mode})")
    print(f"{'=' * 70}")

    by_model: dict[str, list[str]] = {}
    prev_model = None
    for slug, label in ALL_SLUGS:
        model = _resolve(slug)
        source = "phase_models" if get_model_for_phase(slug) else f"defaults[{mode}]"
        if model != prev_model:
            print(f"\n  ── {model}  [{source}]")
            prev_model = model
        print(f"     {slug:<36}  {label}")
        by_model.setdefault(model, []).append(slug)

    print(f"\n{'─' * 70}")
    print(f"  Distinct models: {len(by_model)}")
    for m in by_model:
        print(f"    • {m}  ({len(by_model[m])} phases)")
    print()
    return by_model


# ── Provider ping ─────────────────────────────────────────────────────────────

_PING_MESSAGE = [
    {"role": "system", "content": "You are a connectivity test. Reply with exactly: ok"},
    {"role": "user", "content": 'Reply with the single word "ok" and nothing else.'},
]


def ping_providers(by_model: dict[str, list[str]]) -> bool:
    sys.path.insert(0, str(ROOT / "digigraph" / "src"))
    sys.path.insert(0, str(ROOT / "digillm" / "src"))
    from digigraph.llm_client import completion_text  # noqa: PLC0415

    print(f"{'=' * 70}")
    print("  Provider connectivity check")
    print(f"{'=' * 70}\n")

    all_ok = True
    tested: set[str] = set()
    failures: list[tuple[str, str]] = []

    for model in by_model:
        prov = _provider(model)
        if prov in tested:
            continue
        tested.add(prov)

        # Check required env var
        key_var = {
            "gemini": "GEMINI_API_KEY",
            "ollama-cloud": "OPENAI_API_KEY",
            "openrouter": "OPENROUTER_API_KEY",
        }.get(prov, "OPENAI_API_KEY")
        key_val = os.environ.get(key_var, "").strip()

        if not key_val:
            print(f"  SKIP  {model}")
            print(f"        {key_var} not set — cannot test\n")
            continue

        print(f"  PING  {model}  [{prov}]  … ", end="", flush=True)
        try:
            raw = completion_text(model, _PING_MESSAGE, temperature=0.0, max_tokens=8)
            snippet = (raw or "").strip()[:40] or "(empty)"
            print(f"OK   response={snippet!r}")
        except Exception as exc:
            short = textwrap.shorten(str(exc), width=80)
            print(f"FAIL  {short}")
            failures.append((model, str(exc)))
            all_ok = False
        print()

    if failures:
        print(f"{'─' * 70}")
        print(f"  {len(failures)} provider ping(s) failed:")
        for model, msg in failures:
            print(f"    • {model}: {textwrap.shorten(msg, width=72)}")
        print()

    return all_ok


# ── Entry point ──────────────────────────────────────────────────────────────


def main() -> None:
    ap = argparse.ArgumentParser(
        description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter
    )
    ap.add_argument("--routing", action="store_true", help="Only print routing table")
    ap.add_argument("--ping", action="store_true", help="Only run provider pings")
    args = ap.parse_args()

    do_routing = not args.ping or args.routing
    do_ping = not args.routing or args.ping

    by_model: dict[str, list[str]] = {}
    if do_routing:
        by_model = print_routing_table()
    else:
        # Build by_model without printing
        for slug, _ in ALL_SLUGS:
            m = _resolve(slug)
            by_model.setdefault(m, []).append(slug)

    if do_ping:
        ok = ping_providers(by_model)
        if not ok:
            print("Provider ping failed — check API keys, routing, and network.", file=sys.stderr)
            sys.exit(1)


if __name__ == "__main__":
    main()
