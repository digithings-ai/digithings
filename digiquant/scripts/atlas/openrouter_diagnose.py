#!/usr/bin/env python3
"""OpenRouter diagnostic — root-cause an empty-completion / degraded Atlas run, and report spend.

Runs three checks, cheapest first, and prints a verdict:

  1. Key state  — GET /api/v1/key (works with a standard OPENROUTER_API_KEY): remaining credit,
                  all-time + daily/weekly/monthly usage, free-tier flag, configured limit.
  2. Credits    — GET /api/v1/credits (best-effort: needs a *management* key; 401 → skipped).
  3. Strict ping — one real structured-output (json_schema, strict:true) completion through the
                  SAME digillm path the pipeline uses (so it exercises require_parameters +
                  schema strictification). Reports the model OpenRouter actually served, the
                  per-call USD cost (from the response's ``usage.cost``), and whether the body
                  came back empty (the failure mode we hunt).

Usage:
  python digiquant/scripts/atlas/openrouter_diagnose.py            # full run
  python digiquant/scripts/atlas/openrouter_diagnose.py --no-ping  # account state only (free)

Exit 0 = key reachable and (unless --no-ping) the strict ping produced a non-empty body.
Exit 1 = key unreachable, or the strict ping came back empty (the degraded-run signature).
"""

from __future__ import annotations

import argparse
import math
import os
import sys
import time
from pathlib import Path
from typing import Any  # noqa  # scored-lint: OpenRouter JSON ``data`` objects are heterogeneous

import httpx

_OPENROUTER_BASE = "https://openrouter.ai/api/v1"

_tty = sys.stdout.isatty()


def _c(code: str, s: str) -> str:
    return f"\033[{code}m{s}\033[0m" if _tty else s


def _green(s: str) -> str:
    return _c("32", s)


def _red(s: str) -> str:
    return _c("31", s)


def _yellow(s: str) -> str:
    return _c("33", s)


def _bold(s: str) -> str:
    return _c("1", s)


PASS, FAIL, SKIP = _green("PASS"), _red("FAIL"), _yellow("SKIP")


def _ensure_importable() -> None:
    """Add monorepo src paths to sys.path so digillm/digigraph import when run from the repo."""
    repo_root = Path(__file__).resolve().parents[3]
    for rel in ("digigraph/src", "digillm/src", "digibase/src", "digismith/src"):
        p = str(repo_root / rel)
        if p not in sys.path:
            sys.path.insert(0, p)


# ── pure formatters (unit-tested without network) ─────────────────────────────


def _money(value: Any) -> str:
    """Render a credit/USD amount, or '—' when absent/non-numeric/non-finite.

    float() accepts 'nan'/'inf', which would print a misleading ``$nan``/``$inf`` in operator
    output — treat those (and any non-numeric) as missing."""
    try:
        amount = float(value)
    except (TypeError, ValueError):
        return "—"
    return f"${amount:.4f}" if math.isfinite(amount) else "—"


def summarize_key(data: dict[str, Any]) -> str:
    """One-line summary of GET /api/v1/key's ``data`` object (field names per OpenRouter docs)."""
    limit = data.get("limit")
    remaining = data.get("limit_remaining")
    parts = [
        f"used(all-time)={_money(data.get('usage'))}",
        f"today={_money(data.get('usage_daily'))}",
        f"week={_money(data.get('usage_weekly'))}",
        f"month={_money(data.get('usage_monthly'))}",
        f"limit={'unlimited' if limit is None else _money(limit)}",
        f"remaining={'n/a' if remaining is None else _money(remaining)}",
        f"free_tier={bool(data.get('is_free_tier'))}",
    ]
    return ", ".join(parts)


def key_is_exhausted(data: dict[str, Any]) -> bool:
    """True when a finite credit limit is set and nothing is left — a hard cause of empty bodies."""
    remaining = data.get("limit_remaining")
    try:
        return remaining is not None and float(remaining) <= 0
    except (TypeError, ValueError):
        return False


def summarize_credits(data: dict[str, Any]) -> str:
    """One-line summary of GET /api/v1/credits's ``data`` object."""
    total = data.get("total_credits")
    used = data.get("total_usage")
    balance = None
    try:
        balance = float(total) - float(used)
    except (TypeError, ValueError):
        balance = None
    return (
        f"purchased={_money(total)}, used={_money(used)}, "
        f"balance={'—' if balance is None else _money(balance)}"
    )


# ── checks ────────────────────────────────────────────────────────────────────


def _get_json(path: str, api_key: str) -> dict[str, Any]:
    """GET an OpenRouter endpoint and return its ``data`` object; raise on non-2xx."""
    resp = httpx.get(
        f"{_OPENROUTER_BASE}{path}",
        headers={"Authorization": f"Bearer {api_key}"},
        timeout=30.0,
    )
    resp.raise_for_status()
    payload = resp.json()
    return payload.get("data", payload) if isinstance(payload, dict) else {}


def check_key(api_key: str) -> bool:
    print(_bold("\n1. Key state (GET /api/v1/key)"))
    try:
        data = _get_json("/key", api_key)
    except (httpx.HTTPError, ValueError) as exc:
        print(f"  {FAIL}  key unreachable — {exc}")
        return False
    print(f"  {PASS}  {summarize_key(data)}")
    if key_is_exhausted(data):
        print(f"  {FAIL}  credit limit reached — this alone degrades runs to empty bodies")
        return False
    return True


def check_credits(api_key: str) -> None:
    print(_bold("\n2. Credits (GET /api/v1/credits — needs a management key)"))
    try:
        data = _get_json("/credits", api_key)
    except httpx.HTTPStatusError as exc:
        if exc.response.status_code in (401, 403):
            print(
                f"  {SKIP}  not a management key (HTTP {exc.response.status_code}) — use /key above"
            )
        else:
            print(f"  {SKIP}  {exc}")
        return
    except (httpx.HTTPError, ValueError) as exc:
        print(f"  {SKIP}  {exc}")
        return
    print(f"  {PASS}  {summarize_credits(data)}")


def check_strict_ping() -> bool:
    """Run one strict json_schema completion through the real digillm path; True iff non-empty."""
    print(_bold("\n3. Strict structured-output ping (real digillm path)"))
    try:
        _ensure_importable()
        from pydantic import BaseModel, Field

        from digigraph.graph.research_agent import run_research_agent
        from digigraph import usage as usage_mod

        class _Ping(BaseModel):
            status: str = Field(description="the single word: ok")
            confidence: float = Field(ge=0.0, le=1.0)

        usage_mod.start()
        t0 = time.monotonic()
        out = run_research_agent(
            skill_text="Reply that you are operational.",
            phase_inputs={},
            shared_context={},
            output_model=_Ping,
            model="openrouter/openrouter/auto",
            max_retries=1,
        )
        elapsed = time.monotonic() - t0
        snap = usage_mod.snapshot()
        usage_mod.reset()
        served = (snap.get("models") or ["?"])[0]
        cost = snap.get("cost_usd", 0.0)
        print(
            f"  {PASS}  non-empty body in {elapsed:.1f}s — status={out.status!r}, "
            f"model={served}, cost={_money(cost)}"
        )
        return True
    except Exception as exc:  # noqa: BLE001 — diagnostic: report any failure, never raise
        # An empty body surfaces here as a ValidationError / "empty completion" RuntimeError.
        print(f"  {FAIL}  strict ping failed — {type(exc).__name__}: {exc}")
        print("        → this is the degraded-run signature. Triage: atlas docs/RUNBOOK.md")
        return False


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="OpenRouter diagnostic for Atlas runs.")
    parser.add_argument(
        "--no-ping",
        action="store_true",
        help="Account state only (free) — skip the live strict completion.",
    )
    args = parser.parse_args(argv)

    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        print(f"  {FAIL}  OPENROUTER_API_KEY not set")
        return 1

    key_ok = check_key(api_key)
    check_credits(api_key)
    if args.no_ping:
        print(_bold("\nVerdict:"), "key reachable" if key_ok else "key check FAILED")
        return 0 if key_ok else 1

    ping_ok = check_strict_ping()
    ok = key_ok and ping_ok
    print(_bold("\nVerdict:"), _green("healthy") if ok else _red("degraded — see checks above"))
    return 0 if ok else 1


if __name__ == "__main__":
    raise SystemExit(main())
