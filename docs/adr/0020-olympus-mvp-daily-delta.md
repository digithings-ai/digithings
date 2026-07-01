# ADR 0020: Olympus daily thesis — edit-mode continuity, deterministic sizer, commit_run

**Status:** accepted (amended 2026-06-20)
**Date:** 2026-06-19 · **Amendment:** 2026-06-20

## Context

Jun 17–19 production delta runs cost **147 LLM calls / 726s / $11.95** each, produced three unrelated books (SPY/XLP/IJR → SHY/XLK → BIL) with flat NAV, and the published digest diverged from the materialized `positions`. The learning loop never closed. Root causes (per the Jun-16 architecture audit and Jun-19 forensics):

1. **Hermes is the cost driver, not Atlas.** ~67% of Jun-19 calls were the 7C/7CD fan-out (4 specialists + bull + bear + manager per ticker). ~90% of debates had `conviction_delta = 0` — rubber stamps.
2. **The PM and the deterministic sizer (7E) fight over weights.** PM narrated ~65% invested; 7E landed BIL 30% only. Compounded by phase7e's correlation being hard-stubbed to ρ=1.0, which systematically over-estimates portfolio risk and over-raises cash (audit §6.5).
3. **Five terminal write paths disagree** — publish, materialize, and the post-hoc digest reflected pre-7E narrative while `positions` reflected post-7E sizing.

[ADR-0019](0019-unified-atlas-workflow.md) proposed a unified workflow whose delta strategy assumed **"Hermes phases always re-run on delta — they are cheap relative to research fan-out."** The forensics invalidate that premise: Hermes *is* the dominant delta cost. External benchmarking of comparable autonomous-investing systems (TradingAgents, AlphaAgents, FINCON, virattt/ai-hedge-fund) and the field's cost-evaluation work converge on the same conclusions: optimal coordination is **3–7 agents / 2–3 rounds**, debate only helps when agents genuinely disagree, and the robust pattern is **"LLM proposes, code enforces"** with the sizer as a deterministic feasible-set gate.

### 2026-06-20 amendment trigger

Jun-20 design review ([#930](https://github.com/digithings-ai/digithings/issues/930), absorbing [#924](https://github.com/digithings-ai/digithings/issues/924)) concluded that **graph forks cannot solve continuity or cost**. Even "delta" runs re-generated full documents and re-ran the entire Hermes fan-out. The fix is **artifact-layer continuity** (`resolve_edit_mode` → `DocumentPatch` → programmatic merge) plus **one thesis-aware Hermes graph** (H1–H9) — not `OLYMPUS_HERMES_LITE`, not baseline-vs-delta workflow shapes, and not a second graph builder per cost tier.

## Decision

Adopt a **single daily Olympus graph** for `digiquant.olympus`: Atlas A0–A4 → thesis-aware Hermes H1–H9 → `commit_run`. Graph nodes and edges are **fixed**; cost and continuity vary per LLM call via prompt template, input bundle, output schema (`full` \| `edit` \| `skip`), and post-merge — not via alternate graph builders or cron forks.

1. **One graph, one daily cadence.** No `OLYMPUS_HERMES_LITE`, no `build_hermes_phases_lite`, no parallel full-vs-lite Hermes builders, no `run_type=baseline|delta` graph shapes, no `monthly` run type. Operator "baseline" means intentional full refresh (`refresh_scope=all`, first run, stale prior > `OLYMPUS_STALE_FULL_DAYS`) — not a separate workflow or cron.
2. **Edit-mode continuity.** Per artifact, `resolve_edit_mode` returns `full` \| `edit` \| `skip`. Prior materialized docs drive `edit` (structured `DocumentPatch` + `apply_ops` merge) or `skip` (shallow carry, 0 LLM). Applies to Atlas segments, digest, Hermes analyst payloads, and thesis docs. Quiet-day savings come from `skip` and smaller `edit` outputs — not from collapsing or skipping entire Hermes subgraphs.
3. **Thesis-aware Hermes (H1–H9).** Replace the legacy 4-axis 7C fan-out, bull/bear 7CD stack, and post-PM thesis derivation with: market thesis review/exploration (H1–H2) → vehicle map (H3) → opportunity screener (H4) → unified `AnalystPayload` per ticker (H5) → PM↔analyst deliberation (H6) → PM direction memo (H7) → deterministic 7E sizer (H8) → `commit_run` (H9). Debate is convergence-based (H6), not anonymous bull/bear personas.
4. **PM direction-only + 7E as the deterministic feasible-set sizer** *(unchanged intent from 2026-06-19).* The PM emits direction + conviction ranks + rationale (no weights). 7E owns all magnitudes via a decompose-and-shrink recipe: EWMA vols + Ledoit-Wolf shrinkage-to-constant-correlation (with PSD repair and a thin-history asset-class-bucket fallback), inverse-vol base + bounded conviction tilt + vol-target lever + caps, and no-trade bands. **Cash is a residual of the constraints, not an LLM choice.**
5. **`commit_run` terminal phase** *(unchanged intent from 2026-06-19).* A single phase after 7E upserts `positions`/`nav_history`/`theses` and publishes the operator brief from the **same final post-7E weights**, with an idempotent `decision_log` append and fail-closed coherence checks — so the brief always matches the book. Phase-9 evolution LLM (9A–9C) is **not** on the daily path; beliefs distillation is on-demand only.
6. **Cost control = model tier only.** `OLYMPUS_MODEL_TIER` (`cheap` \| `balanced` \| `quality`) routes LLM nodes via `config/olympus_models.yaml`. Validate cheap-tier JSON reliability ([#926](https://github.com/digithings-ai/digithings/issues/926)) before defaulting edit-mode schemas to `cheap`. Target **≤20 LLM calls** on a quiet day — re-baselined after thesis-first wiring.

This boundary preserves [ADR-0015](0015-atlas-vs-hermes.md): Atlas stays research-only; Hermes owns analysis/allocation; the sizer is deterministic code.

### Superseded provisions (2026-06-19 original, do not implement)

| Original ADR-0020 bullet | Status |
|--------------------------|--------|
| Mode-morphing daily-delta with baseline keeping full graph | **Superseded** — one graph; "baseline" = operator full refresh |
| `OLYMPUS_HERMES_LITE` / `build_hermes_phases_lite` (#931) | **Abandoned** — revert uncommitted #931 work; thesis-first H1–H9 is the only graph |
| `run_type` baseline vs delta as separate Hermes shapes | **Abandoned** — `cadence=daily` + per-artifact edit mode |
| Phase-9 evolution LLM skipped on lite delta path only | **Superseded** — evolution LLM off daily path for all runs; beliefs on-demand |
| Collapse OFF-by-default until #926 | **Refocused** — #926 gates cheap tier for edit-mode nodes, not a lite graph flag |

## Consequences

**Positive:** One topology to maintain; day-over-day artifact continuity; thesis-aware roster and deliberation; published brief always matches `positions`; over-cashing fixed at its mechanism (correlation); cost scales with `skip`/`edit`/`full` per artifact and model tier — not graph forks.

**Negative / tradeoffs:** Larger greenfield refactor than the Jun-19 lite collapse (#931 abandoned); edit fidelity depends on patch quality (schema validation, skills, model tier — no verbatim guard); fewer graph variants mean higher blast radius per node change (mitigated by phased plan steps, per-issue commits, simulator gates); cheap-tier JSON reliability remains load-bearing for `DocumentPatch` outputs (mitigated by #926 + constrained decoding + parse/heal/retry).

## Links

- Epic: [#930](https://github.com/digithings-ai/digithings/issues/930) (absorbs #924); child issues #925, #927–#929, #932, #934–#937; benchmark #926; **abandoned:** #931 lite graph.
- **Canonical spec:** [`docs/superpowers/specs/2026-06-20-olympus-daily-thesis-design.md`](../superpowers/specs/2026-06-20-olympus-daily-thesis-design.md); **plan:** [`docs/superpowers/plans/2026-06-20-olympus-daily-thesis.md`](../superpowers/plans/2026-06-20-olympus-daily-thesis.md).
- **Historical (forensics only):** [`docs/superpowers/specs/2026-06-19-olympus-mvp-delta-design.md`](../superpowers/specs/2026-06-19-olympus-mvp-delta-design.md); [`docs/superpowers/plans/2026-06-19-olympus-mvp-delta.md`](../superpowers/plans/2026-06-19-olympus-mvp-delta.md).
- Supersedes (in part): [ADR-0019](0019-unified-atlas-workflow.md) — its "Hermes always re-runs, it's cheap" delta premise.
- Related: [ADR-0015](0015-atlas-vs-hermes.md) (Atlas/Hermes boundary), [ADR-0010](0010-atlas-first-class-thesis-deliberation.md).
