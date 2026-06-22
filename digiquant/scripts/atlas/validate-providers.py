#!/usr/bin/env python3
"""
Atlas provider validation — run before triggering a real pipeline run.

Checks (in order):
  1. Required env vars are present
  2. OpenRouter connectivity (1-token ping via openrouter/auto)
     Note: all phases route through OpenRouter Auto Router (config/model_modes.yaml).
  3. OpenRouter structured-output routing (real digillm json_schema call)
  3b. OpenRouter function tools — each active-tier phase model accepts the query_data
     tool (guards the ``:online`` "No endpoints found that support tool use" regression)
  4. OpenRouter web search (grounding pre-pass)
  5. Supabase is reachable and daily_snapshots has a prior baseline row
     (required for --auto-baseline on delta runs)
  6. Graph compiles cleanly — dry-run for both baseline and delta

Usage:
  python scripts/validate-providers.py          # from repo root or atlas dir
  python scripts/validate-providers.py --skip-llm  # env-var + DB check only
  python scripts/validate-providers.py --skip-db   # env-var + LLM check only

Exit 0 = all checks passed.
Exit 1 = one or more checks failed (details printed above).
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
import textwrap
import time
from pathlib import Path

# ── colour helpers ─────────────────────────────────────────────────────────────
_tty = sys.stdout.isatty()


def _green(s: str) -> str:
    return f"\033[32m{s}\033[0m" if _tty else s


def _red(s: str) -> str:
    return f"\033[31m{s}\033[0m" if _tty else s


def _yellow(s: str) -> str:
    return f"\033[33m{s}\033[0m" if _tty else s


def _bold(s: str) -> str:
    return f"\033[1m{s}\033[0m" if _tty else s


PASS = _green("PASS")
FAIL = _red("FAIL")
SKIP = _yellow("SKIP")

results: list[tuple[str, bool, str]] = []  # (label, passed, detail)


def check(label: str, passed: bool, detail: str = "") -> bool:
    icon = PASS if passed else FAIL
    line = f"  {icon}  {label}"
    if detail:
        line += f"\n        {detail}"
    print(line)
    results.append((label, passed, detail))
    return passed


# ── resolve repo / package root ────────────────────────────────────────────────
_here = Path(__file__).resolve().parent
_atlas_dir = _here.parent  # digiquant/
_repo_root = _atlas_dir.parent.parent  # repo root


def _ensure_importable() -> None:
    """Add monorepo src paths to sys.path if not already importable."""
    for rel in [
        "digiquant/src",
        "digigraph/src",
        "digibase/src",
        "digismith/src",
    ]:
        p = str(_repo_root / rel)
        if p not in sys.path:
            sys.path.insert(0, p)


# ── individual checks ──────────────────────────────────────────────────────────


def check_env_vars() -> bool:
    print(_bold("\n1. Environment variables"))
    required = {
        "SUPABASE_URL": "Supabase project URL",
        "SUPABASE_SERVICE_ROLE_KEY": "Supabase service-role key",
        "OPENROUTER_API_KEY": "OpenRouter API key (all phases route via Auto Router — see config/model_modes.yaml)",
    }
    all_ok = True
    for var, desc in required.items():
        val = os.environ.get(var, "").strip()
        ok = bool(val)
        check(f"{var}", ok, "" if ok else f"missing — {desc}")
        if not ok:
            all_ok = False
    return all_ok


def check_openrouter(model: str = "openrouter/auto") -> bool:
    print(_bold("\n2. OpenRouter connectivity"))
    api_key = os.environ.get("OPENROUTER_API_KEY", "").strip()
    if not api_key:
        check("OpenRouter ping", False, "OPENROUTER_API_KEY not set — skipping")
        return False
    try:
        from openai import OpenAI

        t0 = time.monotonic()
        client = OpenAI(
            api_key=api_key,
            base_url="https://openrouter.ai/api/v1",
        )
        resp = client.chat.completions.create(
            model=model,
            messages=[{"role": "user", "content": "Reply with the single word: ok"}],
            max_tokens=5,
            temperature=0,
        )
        elapsed = time.monotonic() - t0
        content = resp.choices[0].message.content or ""
        ok = bool(content.strip())
        return check(
            f"OpenRouter {model}",
            ok,
            f"{elapsed:.1f}s — response: {content.strip()!r}" if ok else "empty response",
        )
    except (
        OSError,
        RuntimeError,
        KeyError,
        AttributeError,
        ImportError,
        TypeError,
        ValueError,
    ) as exc:
        return check("OpenRouter ping", False, str(exc))


def check_openrouter_structured() -> bool:
    """Validate the REAL structured-output routing path (digillm + env), not just a plain ping.

    A plain ping (check_openrouter) succeeds even when the model can't honor strict json_schema —
    that's how the pipeline silently degraded (#790/#802). This runs one strict json_schema call
    through the same digillm path the phases use, so any OPENROUTER_ALLOWED_MODELS / require_parameters
    routing misconfig (e.g. the 404 "No models match your request and model restrictions" compound)
    fails the preflight FAST — before the 30-minute pipeline burns a run."""
    print(_bold("\n3. OpenRouter structured-output routing (digillm path)"))
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return check("Structured-output ping", False, "OPENROUTER_API_KEY not set")
    try:
        _ensure_importable()
        from pydantic import BaseModel, Field

        from digigraph import usage as usage_mod
        from digigraph.graph.research_agent import run_research_agent

        class _Ping(BaseModel):
            status: str = Field(description="the single word: ok")

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
        return check(
            "Structured-output ping (openrouter/auto)",
            bool(out.status),
            f"{elapsed:.1f}s — model={served}, cost=${snap.get('cost_usd', 0.0):.4f}",
        )
    except Exception as exc:  # noqa: BLE001 — diagnostic: any failure (incl. OpenRouter HTTP
        # 4xx like the 404 "No models match … model restrictions") must report a clean FAIL,
        # not crash the preflight with a traceback. Catching broadly is correct for a probe.
        return check(
            "Structured-output ping (openrouter/auto)",
            False,
            f"{type(exc).__name__}: {exc}  (routing misconfig — fix before a full run)",
        )


def check_openrouter_function_tools() -> bool:
    """Validate that the active tier's phase models accept FUNCTION TOOLS (``query_data``).

    This is the check that would have caught the ``:online`` regression: structured-output and
    web-search pings both succeed even when the pinned phase model can't do function tools, so the
    pipeline 404'd at runtime with ``No endpoints found that support tool use``. ``:online`` is a
    web-search variant and does NOT imply tool support for open-weight models. Here we send the
    real ``query_data`` tool definitions to EACH distinct model in the active tier's phase pools
    (a stub executor — we only care that OpenRouter accepts the tool request, not the DB read), so
    any non-tool-capable pool member fails the preflight FAST instead of mid-run."""
    print(_bold("\n3b. OpenRouter function tools (phase-model tool capability)"))
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return check("Function-tool smoke test", False, "OPENROUTER_API_KEY not set")
    try:
        _ensure_importable()
        from digigraph.model_config import _load_olympus_models, get_olympus_tier
        from digillm.client import completion
        from digiquant.olympus.atlas.data.tools import DATA_TOOLS

        tier = get_olympus_tier()
        tier_cfg = _load_olympus_models().tiers.get(tier)
        if tier_cfg is None:
            return check("Function-tool smoke test", False, f"unknown tier {tier!r}")
        # Distinct models across all phase (function-tool) pools, order preserved.
        seen: set[str] = set()
        models: list[str] = []
        for pool in tier_cfg.allowed_models.values():
            for m in pool:
                if m not in seen:
                    seen.add(m)
                    models.append(m)
        if not models:
            return check("Function-tool smoke test", False, f"tier {tier!r} has no phase models")

        all_ok = True
        for model in models:
            try:
                t0 = time.monotonic()
                resp = completion(
                    model,
                    [{"role": "user", "content": "Reply with the single word: ok"}],
                    tools=DATA_TOOLS,
                    tool_choice="auto",
                    max_tokens=5,
                    temperature=0,
                )
                elapsed = time.monotonic() - t0
                ok = resp is not None
                check(f"tools accepted: {model}", ok, f"{elapsed:.1f}s" if ok else "no response")
                all_ok = all_ok and ok
            except Exception as exc:  # noqa: BLE001 — a 404 "No endpoints …support tool use" here
                # is exactly the regression we are guarding; report a clean FAIL per-model.
                check(f"tools accepted: {model}", False, f"{type(exc).__name__}: {exc}")
                all_ok = False
        return all_ok
    except Exception as exc:  # noqa: BLE001 — diagnostic probe must not crash preflight
        return check("Function-tool smoke test", False, f"{type(exc).__name__}: {exc}")


def check_openrouter_web_search() -> bool:
    """Validate the OpenRouter ``openrouter:web_search`` server-tool path (Olympus grounding).

    A plain chat ping succeeds even when server tools 404 — that's the alt-/inst-/macro
    ungrounded failure mode. This exercises the same digillm path as ``fetch_web_grounding``."""
    print(_bold("\n4. OpenRouter web search (grounding pre-pass)"))
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return check("Web search ping", False, "OPENROUTER_API_KEY not set")
    try:
        _ensure_importable()
        from digigraph.model_config import get_grounding_model
        from digillm import openrouter_web_search

        model = get_grounding_model() or "openrouter/perplexity/sonar"
        t0 = time.monotonic()
        result = openrouter_web_search(model, "latest US CPI headline release", max_results=3)
        elapsed = time.monotonic() - t0
        ok = result is not None and bool(result[0].strip())
        detail = (
            f"{elapsed:.1f}s — model={model}, sources={len(result[1]) if result else 0}"
            if ok
            else "no grounding text returned (check server-tool routing / grounding_model)"
        )
        return check(f"Web search ({model})", ok, detail)
    except Exception as exc:  # noqa: BLE001 — diagnostic probe must not crash preflight
        return check("Web search ping", False, f"{type(exc).__name__}: {exc}")


def check_supabase() -> bool:
    print(_bold("\n5. Supabase connectivity + baseline row"))
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip()
    if not url or not key:
        check("Supabase ping", False, "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping")
        return False
    try:
        _ensure_importable()
        from digiquant.olympus.atlas.supabase_io import SupabaseConfig, build_client

        t0 = time.monotonic()
        client = build_client(SupabaseConfig.from_env())
        resp = (
            client.table("daily_snapshots")
            .select("date, run_type")
            .eq("run_type", "baseline")
            .order("date", desc=True)
            .limit(1)
            .execute()
        )
        elapsed = time.monotonic() - t0
        rows = getattr(resp, "data", None) or []
        connected = check("Supabase reachable", True, f"{elapsed:.1f}s")
        if rows:
            latest = rows[0]["date"]
            check(
                "Prior baseline exists",
                True,
                f"latest baseline: {latest} — --auto-baseline will resolve",
            )
        else:
            # Informational only — do NOT gate. A baseline run creates the first
            # snapshot; only a delta run with --auto-baseline needs a prior one
            # (the chain's own preflight errors there if truly required). On a
            # fresh/seeded DB this is expected, so it must not fail the preflight.
            print(f"  {SKIP}  Prior baseline exists")
            print("        none yet — OK for a baseline seed; delta --auto-baseline would need one")
        return connected
    except (
        OSError,
        RuntimeError,
        KeyError,
        AttributeError,
        ImportError,
        TypeError,
        ValueError,
    ) as exc:
        return check("Supabase ping", False, str(exc))


def check_dry_run(run_type: str) -> bool:
    print(_bold(f"\n6. Graph dry-run ({run_type})"))
    _ensure_importable()
    today = __import__("datetime").date.today().isoformat()
    cmd = [
        sys.executable,
        "-m",
        "digiquant.olympus.atlas.graph",
        "--run-type",
        run_type,
        "--run-date",
        today,
        "--dry-run",
    ]
    if run_type == "delta":
        cmd.append("--auto-baseline")
    env = {**os.environ, "PYTHONPATH": ":".join(sys.path)}
    t0 = time.monotonic()
    proc = subprocess.run(
        cmd,
        capture_output=True,
        text=True,
        cwd=str(_atlas_dir),
        env=env,
    )
    elapsed = time.monotonic() - t0
    ok = proc.returncode == 0
    detail = f"{elapsed:.1f}s"
    if not ok:
        # Show last few lines of stderr for fast diagnosis
        err_tail = "\n        ".join(proc.stderr.strip().splitlines()[-6:])
        detail += f"\n        stderr: {err_tail}"
    return check(f"Dry-run {run_type}", ok, detail)


# ── main ───────────────────────────────────────────────────────────────────────


def main() -> int:
    parser = argparse.ArgumentParser(
        description="Validate Atlas providers and graph compilation before a real run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Tip: load your local env before running:
              export $(grep -v '^#' digiquant/src/digiquant/olympus/atlas/config/supabase.env | xargs)
              export OPENROUTER_API_KEY=...
        """),
    )
    parser.add_argument("--skip-llm", action="store_true", help="Skip OpenRouter ping")
    parser.add_argument("--skip-db", action="store_true", help="Skip Supabase check")
    parser.add_argument("--skip-dry-run", action="store_true", help="Skip graph dry-run")
    args = parser.parse_args()

    print(_bold("Atlas provider validation"))
    print("─" * 48)

    check_env_vars()

    if not args.skip_llm:
        check_openrouter("openrouter/auto")
        check_openrouter_structured()
        check_openrouter_function_tools()
        check_openrouter_web_search()

    if not args.skip_db:
        check_supabase()

    if not args.skip_dry_run:
        check_dry_run("baseline")
        check_dry_run("delta")

    # Summary
    passed = [r for r in results if r[1]]
    failed = [r for r in results if not r[1]]
    print("\n" + "─" * 48)
    print(f"  {_green(str(len(passed)))} passed   {_red(str(len(failed)))} failed")
    if failed:
        print(_red("\nFailed checks:"))
        for label, _, detail in failed:
            print(f"  • {label}" + (f": {detail}" if detail else ""))
        return 1
    print(_green("\nAll checks passed — safe to trigger a real run."))
    return 0


if __name__ == "__main__":
    sys.exit(main())
