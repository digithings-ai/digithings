# Olympus Second-Pass Redesign — Implementation Plan Index

> **For agentic workers:** each linked plan is self-contained and starts with a Phase-0 presence
> gate (STOP if Phase 0 has not merged). Execute Phase 0 first, then the phases below.
> Spec: `../specs/2026-06-24-olympus-second-pass-redesign-design.md`.

**Goal:** ship the second-pass Olympus redesign — fix the data-layer amputation + single-day
grounding across all surfaces, with Pipeline as the hub every surface links into.

**61 tasks across 8 plans**, all TDD-first, all under `frontend/olympus`, all code-grounded.

| Plan | Phase | Tasks | Net effect |
|---|---|---|---|
| [phase0-foundation](2026-06-24-olympus-phase0-foundation.md) | **0** | 12 | F1 data-layer widening · F2 Why→Pipeline rename + shell/palette/redirects + ⌘K pill + `/pipeline` placeholder · F3 `reconcileBook` · F4 thesis-id join · F5 token rule + guard · F6 `ConvictionMeter`/`SignedConvictionBadge` · F7 canonical `AsOfBadge` · F8 copy sweep · `buildPipelineHref` · 4 backend issues filed |
| [today](2026-06-24-olympus-today.md) | 1 | 6 | Re-ground hero on the read + the book; `WhatToWatch` band; `BookStrip` (reconciled); retire WhyToday; honest NAV |
| [holdings](2026-06-24-olympus-holdings.md) | 1 | 9 | Conviction-first decision-aware table; reconciliation strip; risk-envelope cell; "Proposed by pipeline" shelf; absorbs Position-risk |
| [system](2026-06-24-olympus-system.md) | 1 | 11 | Two zones (live status + reference); D3 run-economics; failed→recovered timeline; per-phase health; deletes phase tables; relocates Attribution/Position-risk |
| [settings](2026-06-24-olympus-settings.md) | 1 | 5 | Status/freshness card; About card; real ⌘K opener; keep theme toggle |
| [theses](2026-06-24-olympus-theses.md) | 2 | 7 | Two-tier research ledger; confirms/breaks criteria columns; holdings linkage; Provenance strip; retire 3rd table |
| [documents](2026-06-24-olympus-documents.md) | 2 | 5 | Defer archive; delete ResearchClient + Knowledge tab; palette cross-day search; distinct-dates>1 gate |
| [performance](2026-06-24-olympus-performance.md) | 3 | 6 | Hybrid tear sheet (live-NAV + decision-track-record); token bridge; client-side `backtest.py` port; absorbs Attribution |

## Build sequence & parallelization

- **Phase 0 (foundation) — first, mostly serial.** Everything depends on it; it edits the shared
  `queries.ts`/`types.ts`/`nav.ts`/palette. Single worktree. Every later plan STOP-gates on it.
- **Phase 1 — parallel (4 surfaces):** Today · Holdings · System · Settings. Disjoint component
  trees → isolated worktrees, run concurrently.
- **Phase 2 — parallel (2 surfaces):** Theses · Documents. After Phase 0 (+ Holdings' decision
  badge, reused by Theses).
- **Phase 3 — last:** Performance. Build the empty-state-first skeleton any time after Phase 0;
  it "goes live" once the D2 backtest-seed lands.

## Execution-coordination notes (cross-plan handoffs the planners surfaced)

1. **Attribution / Position-risk relocation is a hand-off, not a delete.** System (Phase 1)
   *unmounts* `AttributionTab.tsx` and `PositionRiskTab.tsx` from `/observability` but **leaves the
   files on disk**; Holdings imports `PositionRiskTab`, Performance imports `AttributionTab`. The
   System PR must not delete those files. Coordinate the three PRs so the components aren't orphaned
   or double-mounted.
2. **`decision_log.conviction` is −5..+5** (not −2..+3 — fixed in the Phase 0 contract). Buckets key
   off magnitude (HIGH=4, MED=2 per `lib/decision-scorecard.ts`). `SignedConvictionBadge` must not
   clamp. Holdings already tests `+4`.
3. **F5 token guards scope to each surface's own files.** The shared `ConvictionMeter` uses the
   sanctioned accent (`bg-fin-blue` ≡ `--accent` cyan, the one permitted conviction encoding); per-
   surface `fin-blue` grep purges must target their own modified files / allowlist
   `components/shared/`, or they'll false-flag the shared meter.
4. **`/pipeline` is a placeholder that redirects to `/why`** until the separate Pipeline build
   (Surface 1) replaces `app/pipeline/page.tsx`. Coordinate that build with — or after — the Phase 0
   nav flip so users don't land on the legacy Why surface indefinitely.
5. **DB has advanced past the single-day anchor** (now ≥2 NAV points, 2026-06-24 runs exist). All
   empty-state gates are data-driven (`≥2 points`, `distinct-dates>1`, `0 resolved`) so they stay
   honest regardless; test fixtures pin the spec's 2026-06-23 values for stable formatting.
6. **Settings Docs hotfix is already on this branch** (commit `004ac495` → `/system`). Phase 0
   Task 11 + Settings downgrade it to a regression-guard test rather than re-fixing a non-bug.
7. **4 backend issues** (filed in Phase 0 Task 12): weight_pct seeding (D1), backtest-seed (D2),
   canonicalize `positions.thesis_id` (F4), populate `linked_market_thesis_id`. Frontend interims
   (`reconcileBook`, `normalizeThesisId`, "Unlinked expressions" fallback) stand in until they land.
   **D2 gates Performance's populated/demo state** — until seeded, Performance is correctly
   empty-state-only.

## Phase exit gates (every plan)

Full vitest suite green (150+ tests) · `tsc --noEmit` clean · `npx next build` (output:export)
succeeds · F5 grep guards pass · each task ends in a conventional commit with `Refs/Fixes #<N>`.
