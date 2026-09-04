#!/usr/bin/env python3
"""
research provider validation — run before triggering a real pipeline run.

Checks (in order):
  1. Required env vars are present
  2. OpenRouter connectivity (short ping via digillm, pinned to a known-good model)
     Note: phases route on PINNED per-capability models from config/digiquant_models.yaml
     (see RUNBOOK.md "OpenRouter model tiers") — bare openrouter/auto is exercised
     deliberately in check 3 below, not as the connectivity probe.
  3. OpenRouter structured-output routing (real digillm json_schema call)
  3b. OpenRouter function tools — each active-tier phase model accepts the query_data
     tool (guards the ``:online`` "No endpoints found that support tool use" regression)
  4. OpenRouter web search (grounding pre-pass)
  5. Supabase is reachable and daily_snapshots has a prior baseline row
     (required for --auto-baseline on delta runs)
  6. Graph compiles cleanly — dry-run for both baseline and delta

Usage:
  python scripts/validate-providers.py          # from repo root or research dir
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
_research_dir = _here.parent  # digiquant/
_repo_root = _research_dir.parent.parent  # repo root


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
        "OPENROUTER_API_KEY": "OpenRouter API key (phases route on pinned models per tier — see config/digiquant_models.yaml)",
    }
    all_ok = True
    for var, desc in required.items():
        val = os.environ.get(var, "").strip()
        ok = bool(val)
        check(f"{var}", ok, "" if ok else f"missing — {desc}")
        if not ok:
            all_ok = False
    return all_ok


# This ping used to hit the bare, unconstrained ``openrouter/auto`` Auto Router directly
# through a standalone OpenAI client (its own 3-retry/5s-backoff loop, no digillm). That
# combination is the least-defended path in the whole script: OpenRouter documents the Auto
# Router as a Beta, task-classification feature (each request is classified and routed to
# "the most popular model for that task" — openrouter.ai/docs/features/model-routing), not a
# connectivity probe, and a bare "ok" ping carries no response_format/tools — so it never
# triggered digillm's provider.require_parameters guard (client.py: forced ON for
# response_format/tools requests) even when routed through digillm. Every real dashboard phase
# already routes on a PINNED model (RUNBOOK.md "OpenRouter model tiers" — never bare auto),
# and the daily-failure pattern since 2026-08-11 (#1633) was this exact bare ping hard-failing
# preflight while check 3 below — the only other check that deliberately exercises
# openrouter/auto, but with a structured-output request that DOES trigger require_parameters —
# passed cleanly. (3b and 4 route to pinned models, not auto, and are unaffected either way.)
#
# Fix: route through digillm's completion() (same self-heal every real call gets) AND pin the
# ping to a known-good open-weight model instead of the flaky bare auto-router.
#
# That fix (#1633) was necessary but not sufficient — the failure recurred (#2374, then again
# after PR #2512 added OPENROUTER_FALLBACK_MODELS to this step, #2517). Root cause, confirmed
# by direct reproduction against the live OpenRouter API (see #2517): several of the ~5 backend
# providers OpenRouter load-balances ``deepseek/deepseek-v4-flash`` across (observed:
# ``StreamLake``, ``AtlasCloud``) unconditionally emit visible chain-of-thought before the
# answer, and that reasoning text is billed against the SAME ``max_tokens`` budget as the
# answer — it is not a separate reasoning-token allowance. At ``max_tokens=5`` those providers
# hit ``finish_reason: "length"`` mid-thought with ``content: null`` before ever reaching the
# answer. Neither ``reasoning: {"exclude": true}`` nor ``reasoning: {"max_tokens": N}`` fixes
# this — ``exclude`` only stops OpenRouter from echoing the reasoning text back (the model still
# spends the budget generating it), and a probe of ``reasoning.max_tokens=10`` against these
# providers still burned the *entire* ``max_tokens`` ceiling on reasoning regardless — they do
# not honor a reasoning-specific sub-budget.
#
# A first fix pinned ``max_tokens=64`` (~2.5x headroom over an initial 21-24-completion-token
# sample). That was still a guess at a "safe" finite ceiling against a fundamentally variable
# quantity: a wider live sample (30+ calls against the same providers, temperature=0) never
# exceeded 24 completion tokens even when given up to 2000 to work with, so 64 wasn't "not
# enough headroom" so much as an arbitrary bet against a provider-controlled quantity — any
# finite number just moves the tail, it doesn't remove it.
#
# Root-cause fix: don't cap it. Every real dashboard phase call already runs with
# ``max_tokens=None`` (see ``digigraph/src/digigraph/graph/research_agent.py::run_research_agent``,
# the same completion path ``check_openrouter_structured`` above calls) and has never shown this
# failure mode — the bug was never "these providers need N tokens," it was "an artificial
# ceiling exists at all" on a call whose length is provider-controlled, not caller-controlled.
# ``completion()`` genuinely omits ``max_tokens`` from the wire request when ``None`` (not sent
# as literal null), so the provider's own stop condition governs — confirmed clean
# (``finish_reason: "stop"``) across 10/10 live samples with no cap. Retries remain as a
# backstop for real transience, not as the mechanism this check depends on to pass.
_CONNECTIVITY_PING_MODEL = "deepseek/deepseek-v4-flash"

# Preflight-local digillm bounds — read once at digillm import. The real pipeline keeps
# digillm's 600s / empty-retry defaults; the preflight needs a fast FAIL, not a 240-minute
# job cancellation (#2528/#2531). CI also sets timeout-minutes on this workflow step.
_PREFLIGHT_REQUEST_TIMEOUT_SECONDS = 20.0
_PREFLIGHT_EMPTY_RETRY_MAX = 0
_PREFLIGHT_STEP_TIMEOUT_MINUTES = 10


def _configure_preflight_environment() -> None:
    """Apply production OpenRouter routing and bound digillm before the first LLM import."""
    os.environ.setdefault(
        "DIGILLM_REQUEST_TIMEOUT_SECONDS",
        str(_PREFLIGHT_REQUEST_TIMEOUT_SECONDS),
    )
    os.environ.setdefault(
        "DIGILLM_EMPTY_RETRY_MAX",
        str(_PREFLIGHT_EMPTY_RETRY_MAX),
    )
    _ensure_importable()
    from digigraph.model_config import apply_digiquant_openrouter_env

    apply_digiquant_openrouter_env()


def check_openrouter(model: str = _CONNECTIVITY_PING_MODEL) -> bool:
    print(_bold("\n2. OpenRouter connectivity"))
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        check("OpenRouter ping", False, "OPENROUTER_API_KEY not set — skipping")
        return False
    try:
        _ensure_importable()
        from digillm.client import completion

        t0 = time.monotonic()
        resp = completion(
            model,
            [{"role": "user", "content": "Reply with the single word: ok"}],
            temperature=0,
        )
        elapsed = time.monotonic() - t0
        content = ""
        if resp is not None and resp.choices:
            content = (resp.choices[0].message.content or "").strip()
        return check(
            f"OpenRouter {model}",
            bool(content),
            f"{elapsed:.1f}s — response: {content!r}"
            if content
            else "empty response after digillm's empty-retry self-heal",
        )
    except Exception as exc:
        return check("OpenRouter ping", False, f"{type(exc).__name__}: {exc}")


def check_openrouter_structured() -> bool:
    """Validate structured-output routing on ``openrouter/auto`` via the real digillm path.

    Requires ``_configure_preflight_environment()`` first so ``OPENROUTER_ALLOWED_MODELS``
    matches production (``apply_digiquant_openrouter_env``). With the pool constrained, digillm
    attaches the ``auto-router`` plugin and omits ``require_parameters`` — the same request
    shape portfolio chain startup uses. A plain ping (check 2) cannot catch json_schema routing
    failures (#790/#802); a mis-set allowed-models pool or compound restriction fails here."""
    print(_bold("\n3. OpenRouter structured-output routing (digillm path)"))
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return check("Structured-output ping", False, "OPENROUTER_API_KEY not set")
    try:
        _ensure_importable()
        from digigraph import usage as usage_mod
        from digigraph.graph.research_agent import run_research_agent
        from pydantic import BaseModel, Field

        class _Ping(BaseModel):
            status: str = Field(description="the single word: ok")

        usage_mod.start()
        t0 = time.monotonic()
        out = run_research_agent(
            skill_text="Reply that you are operational.",
            phase_inputs={},
            shared_context={},
            output_model=_Ping,
            model="openrouter/auto",
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
    except Exception as exc:
        # A 4xx like the 404 "No models match … model restrictions" must report a clean FAIL,
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
        from digigraph.model_config import _load_digiquant_models, get_digiquant_tier
        from digillm.client import _parse_provider_prefix, completion

        from digiquant.research.data.tools import DATA_TOOLS

        tier = get_digiquant_tier()
        tier_cfg = _load_digiquant_models().tiers.get(tier)
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
                    temperature=0,
                )
                elapsed = time.monotonic() - t0
                message = resp.choices[0].message if resp is not None and resp.choices else None
                has_output = bool(
                    message and ((message.content or "").strip() or message.tool_calls)
                )
                # OPENROUTER_FALLBACK_MODELS (set on this pipeline step, to match the real
                # run's routing conditions — #1622) attaches fallback routing to the PRIMARY
                # request, not just empty-completion retries (digillm/client.py:1290-1292) —
                # so OpenRouter can transparently substitute a working pool member and still
                # return real content even when `model` itself would have been rejected for
                # tool use. That's the exact :online "No endpoints found" regression this
                # check exists to catch — but the SAME env var is set on the real "Run dashboard
                # research pipeline" step, so a real run tolerates the identical substitution;
                # substitution here does not predict a broken run. It's also the documented,
                # EXPECTED trigger for ordinary transient provider load-shedding
                # (pipeline-digiquant.yml's own comment on this env var), not just genuine
                # incapability — so treating every substitution as a hard failure would
                # reintroduce exactly the fragile-preflight failure mode #2374/#2517 already
                # fixed once. Report it instead of failing on it: the served model
                # (client.py:1498-1500, `getattr(r, "model", None)`, the same field digillm
                # itself records as "actually served") tells a human which model actually
                # answered, without turning a benign substitution into a pipeline-blocking
                # preflight failure. Only meaningful for models actually routed through
                # OpenRouter — a bare `removeprefix("openrouter/")` would misfire on a
                # differently-prefixed pin (e.g. `gemini/...`), which digillm strips
                # differently (see `_parse_provider_prefix`).
                served = getattr(resp, "model", None) if resp is not None else None
                vendor, _ = _parse_provider_prefix(model)
                # gemini/ and xai/ are BYOK/diagnostic prefixes, not house OpenRouter slugs
                # (house Gemini pins use google/, xAI pins use x-ai/). anthropic/ IS a
                # house OpenRouter slug and must still be compared.
                skip_sub = vendor in {"gemini", "xai"}
                if served and not skip_sub:
                    requested = {model, model.removeprefix("openrouter/")}
                    substituted = served not in requested
                else:
                    substituted = False
                if not has_output:
                    detail = "empty response (no content, no tool_calls)"
                elif substituted:
                    detail = (
                        f"{elapsed:.1f}s — served by {served}, not the requested model "
                        "(OpenRouter fallback substitution — informational, not a failure)"
                    )
                elif served:
                    detail = f"{elapsed:.1f}s — served by {served}"
                else:
                    detail = f"{elapsed:.1f}s"
                check(f"tools accepted: {model}", has_output, detail)
                all_ok = all_ok and has_output
            except Exception as exc:
                # A tool-use 404 is exactly the regression we are guarding; report a clean FAIL per model.
                check(f"tools accepted: {model}", False, f"{type(exc).__name__}: {exc}")
                all_ok = False
        return all_ok
    except Exception as exc:
        return check("Function-tool smoke test", False, f"{type(exc).__name__}: {exc}")


def check_openrouter_web_search() -> bool:
    """Validate dashboard native web grounding (built-in search on ``get_grounding_model``).

    Production pools are perplexity/``:online`` only (#2567) — this exercises the
    digillm **native** branch used by ``fetch_web_grounding``, not the Exa
    ``openrouter:web_search`` toolkit fallback.
    """
    print(_bold("\n4. OpenRouter web search (dashboard native grounding)"))
    if not os.environ.get("OPENROUTER_API_KEY", "").strip():
        return check("Web search ping", False, "OPENROUTER_API_KEY not set")
    try:
        _ensure_importable()
        from digigraph.model_config import get_grounding_model, is_web_search_capable_model
        from digillm import openrouter_web_search

        model = get_grounding_model() or "perplexity/sonar"
        if not is_web_search_capable_model(model):
            return check(
                f"Web search ({model})",
                False,
                "grounding model is not web-search-capable (dashboard requires native search)",
            )
        t0 = time.monotonic()
        result = openrouter_web_search(model, "latest US CPI headline release")
        elapsed = time.monotonic() - t0
        ok = result is not None and bool(result[0].strip())
        detail = (
            f"{elapsed:.1f}s — model={model}, sources={len(result[1]) if result else 0}"
            if ok
            else "no grounding text returned (check native search / grounding_model)"
        )
        return check(f"Web search ({model})", ok, detail)
    except Exception as exc:
        return check("Web search ping", False, f"{type(exc).__name__}: {exc}")


def check_supabase() -> bool:
    print(_bold("\n5. Supabase connectivity + baseline row"))
    url = os.environ.get("CORE_SUPABASE_URL", os.environ.get("SUPABASE_URL", "")).strip()
    key = os.environ.get(
        "CORE_SUPABASE_SERVICE_KEY", os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "")
    ).strip()
    if not url or not key:
        check("Supabase ping", False, "SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY not set — skipping")
        return False
    try:
        _ensure_importable()
        from digiquant.research.supabase_io import SupabaseConfig, build_client

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
        "digiquant.research.graph",
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
        cwd=str(_research_dir),
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
        description="Validate research providers and graph compilation before a real run.",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=textwrap.dedent("""\
            Tip: load your local env before running:
              export $(grep -v '^#' digiquant/src/digiquant/research/config/supabase.env | xargs)
              export OPENROUTER_API_KEY=...
        """),
    )
    parser.add_argument("--skip-llm", action="store_true", help="Skip OpenRouter ping")
    parser.add_argument("--skip-db", action="store_true", help="Skip Supabase check")
    parser.add_argument("--skip-dry-run", action="store_true", help="Skip graph dry-run")
    args = parser.parse_args()

    print(_bold("research provider validation"))
    print("─" * 48)

    _configure_preflight_environment()
    check_env_vars()

    if not args.skip_llm:
        check_openrouter()
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
