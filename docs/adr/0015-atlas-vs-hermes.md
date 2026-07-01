# ADR-0015 — Atlas vs Hermes responsibility boundary

- **Status:** Accepted (amended 2026-06-20)
- **Date:** 2026-04-28
- **Related epic:** [#471](https://github.com/digithings-ai/digithings/issues/471) · [#930](https://github.com/digithings-ai/digithings/issues/930) (thesis-first Hermes)
- **Amends:** [ADR-0014](0014-atlas-in-digiquant.md) (Atlas in `digiquant/` is preserved; this ADR splits the Atlas package itself).

## Context

After [ADR-0014](0014-atlas-in-digiquant.md) folded Atlas into the `digiquant`
module, the package `digiquant.olympus.atlas` ended up doing two distinct jobs:

1. **Research.** Phases 1 → 7a (alt-data, institutional, macro, asset-class,
   equities, consolidation, master synthesis) — discovering and summarising
   market state.
2. **Analysis + portfolio mgmt.** Thesis-aware Hermes **H1–H9** — market thesis
   review/exploration, vehicle map, opportunity screener, unified asset analyst,
   PM↔analyst deliberation, PM direction memo, deterministic risk sizing, and
   `commit_run` terminal booking — turning research into allocation and persisted
   positions.

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

Split `digiquant.olympus.atlas` into two sibling sub-packages:

- **`digiquant.olympus.atlas`** — research only. **A0–A4:** preflight,
  triage, phases 1–5 segments, phase6 consolidate, phase7 digest. Edit-mode
  continuity via `resolve_edit_mode` per artifact.
- **`digiquant.olympus.hermes`** — thesis-aware portfolio loop. **H1–H9:**
  thesis review → exploration → vehicle map → screener → asset analyst →
  deliberation → PM direction → risk sizing (H8) → **`commit_run`** (H9 terminal).
  Consumes the Atlas digest; books positions and publishes the operator brief
  from the same H8 weights.

The handoff seam is `digiquant.olympus.atlas.snapshot.DigestPayload`. Atlas
writes a `DigestPayload`; Hermes reads one. That is the **only** shared symbol
between the two packages.

```
                    DigestPayload
Atlas (research) ───────────────► Hermes (H1–H9)
   A0–A4                              ends at commit_run (H9)
   ends at phase7_synthesis           H9 upserts positions/nav/theses + brief
```

### Import direction rule

```
digiquant.olympus.atlas    ← never imports from digiquant.olympus.hermes
digiquant.olympus.hermes   ← imports only digiquant.olympus.atlas.snapshot.DigestPayload
                     (and the digest-relevant pydantic subtypes it re-exports)
```

A test enforces this at collection time (no `from digiquant.olympus.hermes` lines
inside `digiquant/src/digiquant/olympus/atlas/`).

### Skill split

Skills live next to whichever engine loads them at runtime. The split is
caller-side (whoever's `load_skill(slug)` opens the file), not subject-side.

- **`digiquant/src/digiquant/olympus/atlas/skills/`** — research, data fetch, daily/weekly/monthly
  cadence, asset analysts, sector research, digest, orchestrator, news.
- **`digiquant/src/digiquant/olympus/hermes/skills/`** — thesis, market-thesis-exploration,
  thesis-vehicle-map, opportunity-screener, asset-analyst, deliberation, pm-direction,
  plus `*-full.md` / `*-edit.md` variants for edit-mode continuity.

**Historical (removed from daily graph):** 4-axis analysts, bull/bear debate,
risk-aggressive/conservative personas, phase9 evolution LLM on daily path.

Skills that straddle (e.g., `asset-analyst` is referenced from both research
and analysis paths) stay in Atlas; Hermes copies are only created where
prompts genuinely diverge.

### Templates / JSON schemas

Same caller-side rule: schemas validated by Atlas runtime stay in
`digiquant/src/digiquant/olympus/atlas/templates/`; schemas validated by Hermes phases move to
`digiquant/src/digiquant/olympus/hermes/templates/`.

### Top-level orchestration

Two CLIs:

- `python -m digiquant.olympus.atlas.graph` — research only.
- `python -m digiquant.olympus.hermes.graph --from-digest <path>` — Hermes only,
  consuming a saved digest.
- `python -m digiquant.olympus.hermes.chain --cadence daily` —
  end-to-end Atlas A0–A4 → Hermes H1–H9 → `publish_phase` (Atlas artifacts) with
  H9 `commit_run` terminal booking. Cron: `.github/workflows/pipeline-olympus.yml`.

**Deprecated CLI shims:** `--run-type baseline|delta` (warns); `monthly` rejected.
Operator full refresh: `--refresh-scope all` — not a separate graph.

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
  `digiquant.olympus.atlas.snapshot` is import-light by design (no LangGraph, no
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
