# ADR-0015 — Atlas vs Hermes responsibility boundary

- **Status:** Accepted
- **Date:** 2026-04-28
- **Related epic:** [#471](https://github.com/digithings-ai/digithings/issues/471)
- **Amends:** [ADR-0014](0014-atlas-in-digiquant.md) (Atlas in `digiquant/` is preserved; this ADR splits the Atlas package itself).

## Context

After [ADR-0014](0014-atlas-in-digiquant.md) folded Atlas into the `digiquant`
module, the package `digiquant.atlas` ended up doing two distinct jobs:

1. **Research.** Phases 1 → 7a (alt-data, institutional, macro, asset-class,
   equities, consolidation, master synthesis) — discovering and summarising
   market state.
2. **Analysis + portfolio mgmt.** Phases 7c (4-axis analyst), 7cd (Bull/Bear
   debate), 7d (risk-aggressive vs conservative debate + PM allocation memo),
   9 (closed-loop reflection / alpha scoring) — turning research into bias,
   allocation, and reflection.

These are different concerns with different cadence, different reviewers, and
different consumers. Research output (the daily digest) is useful on its
own — SITAAS-style users want it without the analysis layer. Analysis is
useless without research, but it should evolve independently: swap analysts,
add risk personalities, change the PM algorithm, all without touching
research code. Today they share a state object, a graph, and a skill tree,
which makes both harder to evolve.

The product taxonomy already names the analysis engine **Hermes**
(see [docs/projects](../projects/) and the marketing-side memos). The code
just hadn't caught up.

## Decision

Split `digiquant.atlas` into two sibling sub-packages:

- **`digiquant.atlas`** — research only. Phases 1–7a, plus the support
  phases (`triage_phase`, `phase_monthly`, `preflight`, `publish_phase`).
  Terminates at `phase7_synthesis`. Owns the snapshot publish path.
- **`digiquant.hermes`** *(new)* — analysis + portfolio mgmt + risk +
  reflection. Phases 7c, 7cd, 7d, 9. Consumes the Atlas digest, produces
  analyst reports, an allocation memo, and a reflection record.

The handoff seam is the existing `digiquant.atlas.snapshot.DigestPayload`
contract. Atlas writes a `DigestPayload`; Hermes reads one. That is the
**only** shared symbol between the two packages.

```
                    DigestPayload
Atlas (research) ───────────────► Hermes (analysis + PM)
   phases 1..7a                      phases 7c, 7cd, 7d, 9
   ends at phase7_synthesis          ends at phase9_evolution
   writes daily_snapshots            writes documents (Thesis Review,
                                     Allocation Memo, Reflection)
```

### Import direction rule

```
digiquant.atlas    ← never imports from digiquant.hermes
digiquant.hermes   ← imports only digiquant.atlas.snapshot.DigestPayload
                     (and the digest-relevant pydantic subtypes it re-exports)
```

A test enforces this at collection time (no `from digiquant.hermes` lines
inside `digiquant/src/digiquant/atlas/`).

### Skill split

Skills live next to whichever engine loads them at runtime. The split is
caller-side (whoever's `load_skill(slug)` opens the file), not subject-side.

- **`digiquant/atlas/skills/`** — research, data fetch, daily/weekly/monthly
  cadence, asset analysts, sector research, digest, orchestrator, news.
- **`digiquant/hermes/skills/`** — analyst specialists used by phase7c
  (fundamental, technical, sentiment), Bull/Bear debate, PM allocation memo,
  portfolio manager, risk-aggressive/conservative, decision-reflector,
  pipeline-evolution, thesis lifecycle, deliberation, opportunity-screener.

Skills that straddle (e.g., `asset-analyst` is referenced from both research
and analysis paths) stay in Atlas; Hermes copies are only created where
prompts genuinely diverge.

### Templates / JSON schemas

Same caller-side rule: schemas validated by Atlas runtime stay in
`digiquant/atlas/templates/`; schemas validated by Hermes phases move to
`digiquant/hermes/templates/`.

### Top-level orchestration

Two CLIs:

- `python -m digiquant.atlas.graph --run-type baseline|delta|monthly` —
  research only.
- `python -m digiquant.hermes.graph --from-digest <path>` — analysis only,
  consuming a saved digest.
- `python -m digiquant.hermes.chain --run-type baseline|delta|monthly` —
  the existing end-to-end behaviour. Runs Atlas, hands the digest to
  Hermes. The cron workflows
  (`atlas-baseline.yml` / `atlas-delta.yml` / `atlas-monthly.yml`) switch to
  this entry point so production behaviour is unchanged.

## Consequences

**Positive**

- Clear architectural boundary at the digest contract.
- Hermes can swap analysts / add risk personalities / change the PM
  algorithm without touching Atlas.
- SITAAS-style consumers can install / depend on research without pulling
  the analysis stack.
- Test scope splits cleanly: `tests/dq/atlas/` and `tests/dq/hermes/`,
  each gated by their own conftest on monorepo-deps availability.
- Documentation matches product taxonomy — Atlas means research, Hermes
  means analysis.

**Negative / tradeoffs**

- One more package to maintain. Mitigated by sharing build infra (single
  `digiquant/pyproject.toml` covers both; `[atlas]` extras pull what both
  engines need).
- Cron workflow CLIs change (atlas-baseline → hermes-chain). Manageable,
  documented in the migration ticket.
- Some cross-cutting code (state types) duplicates a bit. Worth the
  decoupling.
- Future "Atlas-only" SITAAS deployment must still pip-install `digiquant`
  to get the digest contract — not a separate package. Acceptable, since
  `digiquant.atlas.snapshot` is import-light by design (no LangGraph, no
  supabase).

## Migration

Tracked in epic [#471](https://github.com/digithings-ai/digithings/issues/471).
Six child tasks:

1. [#477](https://github.com/digithings-ai/digithings/issues/477) — this ADR.
2. [#472](https://github.com/digithings-ai/digithings/issues/472) — Hermes Python package + phase moves.
3. [#473](https://github.com/digithings-ai/digithings/issues/473) — Hermes graph + atlas→hermes chain.
4. [#474](https://github.com/digithings-ai/digithings/issues/474) — Skills + templates split.
5. [#475](https://github.com/digithings-ai/digithings/issues/475) — Test split.
6. [#478](https://github.com/digithings-ai/digithings/issues/478) — Docs reshape.
7. [#476](https://github.com/digithings-ai/digithings/issues/476) — CI path filters.

## Links

- Predecessor: [ADR-0014](0014-atlas-in-digiquant.md)
- Frontend umbrella: [ADR-0009](0009-frontend-umbrella.md)
- Atlas snapshot contract: [ADR-0008](0008-atlas-research-schema.md)
