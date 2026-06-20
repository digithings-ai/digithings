# ADR 0020: Olympus MVP daily-delta — Hermes-lite collapse, deterministic sizer, commit_run

**Status:** accepted
**Date:** 2026-06-19

## Context

Jun 17–19 production delta runs cost **147 LLM calls / 726s / $11.95** each, produced three unrelated books (SPY/XLP/IJR → SHY/XLK → BIL) with flat NAV, and the published digest diverged from the materialized `positions`. The learning loop never closed. Root causes (per the Jun-16 architecture audit and Jun-19 forensics):

1. **Hermes is the cost driver, not Atlas.** ~67% of Jun-19 calls were the 7C/7CD fan-out (4 specialists + bull + bear + manager per ticker). ~90% of debates had `conviction_delta = 0` — rubber stamps.
2. **The PM and the deterministic sizer (7E) fight over weights.** PM narrated ~65% invested; 7E landed BIL 30% only. Compounded by phase7e's correlation being hard-stubbed to ρ=1.0, which systematically over-estimates portfolio risk and over-raises cash (audit §6.5).
3. **Five terminal write paths disagree** — publish, materialize, and the post-hoc digest reflected pre-7E narrative while `positions` reflected post-7E sizing.

[ADR-0019](0019-unified-atlas-workflow.md) proposed a unified workflow whose delta strategy assumed **"Hermes phases always re-run on delta — they are cheap relative to research fan-out."** The forensics invalidate that premise: Hermes *is* the dominant delta cost. External benchmarking of comparable autonomous-investing systems (TradingAgents, AlphaAgents, FINCON, virattt/ai-hedge-fund) and the field's cost-evaluation work converge on the same conclusions: optimal coordination is **3–7 agents / 2–3 rounds**, debate only helps when agents genuinely disagree, and the robust pattern is **"LLM proposes, code enforces"** with the sizer as a deterministic feasible-set gate.

## Decision

Adopt a **mode-morphing daily-delta architecture** for Olympus (`digiquant.olympus`), shipped behind flags. **Baseline (weekly) keeps the full graph;** the lite/collapse path is for delta and is **OFF-by-default until the open-weight JSON-reliability benchmark ([#926](https://github.com/digithings-ai/digithings/issues/926)) validates the cheap tier.**

1. **Hermes-lite graph collapse** (`OLYMPUS_HERMES_LITE`) — on delta, one unified analyst call/ticker → one PM call → deterministic 7E; debate gated (`HERMES_DEBATE_GATING`) so 7CD runs only on genuine disagreement; Phase-9 evolution LLM skipped. Target **<20 LLM calls / <$1.50** on the cheap tier. The cheap learning-loop resolver (`preflight_reflect`) is preserved — only the Phase-9 improvement-proposals artifact goes dark on delta.
2. **PM direction-only + 7E as the deterministic feasible-set sizer.** The PM emits direction + conviction ranks + rationale (no weights). 7E owns all magnitudes via a decompose-and-shrink recipe: EWMA vols + Ledoit-Wolf shrinkage-to-constant-correlation (with PSD repair and a thin-history asset-class-bucket fallback), inverse-vol base + bounded conviction tilt + vol-target lever + caps, and no-trade bands. **Cash is a residual of the constraints, not an LLM choice** — this removes the over-cashing failure mode.
3. **`commit_run` terminal phase.** A single phase after 7E upserts `positions`/`nav_history`/`theses` and publishes the operator brief from the **same final post-7E weights**, with an idempotent `decision_log` append and fail-closed coherence checks — so the brief always matches the book.

This boundary preserves [ADR-0015](0015-atlas-vs-hermes.md): Atlas stays research-only; Hermes owns analysis/allocation; the sizer is deterministic code.

## Consequences

**Positive:** ~7× cost reduction on delta; the published brief always matches `positions`; over-cashing fixed at its mechanism (correlation); the book evolves day-over-day instead of churning; baseline fidelity is untouched.

**Negative / tradeoffs:** fewer, higher-stakes LLM calls make per-call JSON reliability load-bearing on cheap open-weight models (mitigated by #926 + constrained decoding + a parse/heal/retry net, and by keeping the collapse OFF-by-default until validated); the bull/bear deliberation surface thins on quiet delta days (mitigated — full debate still runs on high-conviction / sell / changed-stance days, and carried states render as explicit "no material change"); higher blast radius on the terminal write path and the sizer (mitigated by flags, per-issue commits, and the simulator exit gates).

## Links

- Epic: [#930](https://github.com/digithings-ai/digithings/issues/930); child issues #925, #927–#929, #931–#937; deferred #924; benchmark #926.
- Spec: [`docs/superpowers/specs/2026-06-19-olympus-mvp-delta-design.md`](../superpowers/specs/2026-06-19-olympus-mvp-delta-design.md); plan: [`docs/superpowers/plans/2026-06-19-olympus-mvp-delta.md`](../superpowers/plans/2026-06-19-olympus-mvp-delta.md).
- Supersedes (in part): [ADR-0019](0019-unified-atlas-workflow.md) — its "Hermes always re-runs, it's cheap" delta premise.
- Related: [ADR-0015](0015-atlas-vs-hermes.md) (Atlas/Hermes boundary), [ADR-0010](0010-atlas-first-class-thesis-deliberation.md).
