# Olympus Track A / B mini-plan

> **Date:** 2026-08-25  
> **Parent epic:** [#1950](https://github.com/digithings-ai/digithings/issues/1950)  
> **Product shape:** [vision realignment brief](2026-08-25-olympus-vision-realignment-brief.md)  
> **Phase 0 tasks:** [observability & accounting plan](2026-08-06-olympus-pipeline-phase0-observability-accounting.md)  
> **Do not:** implement WP3 code from this document; Tracks B/C are bullets only.

---

## Track A — in flight (trust / money)

Close WP2 hollowness, then run period-correct NAV/attribution (WP3).

| Item | Issue | Role |
|------|-------|------|
| Metaplan / product-intent docs | [#2588](https://github.com/digithings-ai/digithings/issues/2588) | Docs — amend olympus metaplan with 2026-08-25 product intent |
| Label legacy reconstruction | [#2422](https://github.com/digithings-ai/digithings/issues/2422) / [#2594](https://github.com/digithings-ai/digithings/issues/2594) | WP2 residual — `book_source` / compatibility views |
| Seed lots + cutover | [#2589](https://github.com/digithings-ai/digithings/issues/2589) / [#2595](https://github.com/digithings-ai/digithings/issues/2595) | Seed `portfolio_ledger_holding_lots`; remove `--no-ledger`; prefer `--require-ledger` |

**Gate before selling NAV as authoritative:** seed/cutover + labeling coherent; then WP3 shadow reconcile before public reader cutover.

---

## Track A — next (WP3 filed)

Period-correct NAV and attribution. Source: Phase 0 plan Work Package 3. Migration numbers only after syncing `module/digiquant`; schema migration **after 070**.

| Task | Issue | Risk | Notes |
|------|-------|------|-------|
| 3.1 Accounting contracts, schema, pure engine (`OLY-REV-007/008`) | [#2596](https://github.com/digithings-ai/digithings/issues/2596) | high | Decimal/Polars engine; migration after 070 |
| 3.2 Persist EOD holdings / periods / NAV / attribution | [#2597](https://github.com/digithings-ai/digithings/issues/2597) | high | Atomic finalizer; no provisional-as-final |
| 3.3 Separate current-book lookback from realized attribution | [#2598](https://github.com/digithings-ai/digithings/issues/2598) | med | `current_book_lookback` vs `daily_realized_attribution` |
| 3.4 Curated views + reader cutover after shadow reconcile | [#2599](https://github.com/digithings-ai/digithings/issues/2599) | med | Land last; rollback = repoint view/adapter |

**Order:** 3.1 → 3.2 → 3.3 (can overlap naming with 3.2) → 3.4 after shadow gate.

> **Duplicate notice:** [#2590](https://github.com/digithings-ai/digithings/issues/2590)–[#2593](https://github.com/digithings-ai/digithings/issues/2593) are earlier WP3.1–3.4 filings under the same epic. Prefer **#2596–#2599** as the active set (fuller agent_task bodies); close or supersede #2590–#2593 when convenient so agents do not double-implement.

---

## Track B — later (research plumbing; do not implement yet)

Pull forward beside Track A when capacity allows — **not** after WP8–10; **do not start from this mini-plan**.

- **ProfileConfig / PipelineProfile** — DB-backed investment overlay seam; house default run always-on and immutable; UI read-only pins first.
- **Shared corpus (WP12-class)** — tenant-agnostic keys (`theme:` / `asset:` / `segment:`); publish-if-missing; never fork per user.
- **Planner shadow (WP13-class shadow)** — LLM cadence / refresh reasons visible; cannot expand H4 or rewrite H7/H8; shadow only (not full canary gates).

---

## Track C — note only

- [#1945](https://github.com/digithings-ai/digithings/issues/1945) — Olympus Pipeline as complete glass-box run inspector (product surface beside Brief). Parallel to A/B; does not substitute for honest money (Track A) or corpus/planner plumbing (Track B).

---

## Explicit non-goals (this doc)

- No WP3 implementation.
- No live-trading / broker / digikey changes.
- No Track B/C code or issue filing from this mini-plan alone.
