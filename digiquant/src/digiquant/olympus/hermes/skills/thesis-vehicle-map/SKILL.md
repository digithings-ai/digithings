---
name: thesis-vehicle-map
description: >
  Track B Phase 2 — map market theses to candidate ETF vehicles using user mandate, watchlist, and
  investment profile. Produces thesis_vehicle_map JSON. Triggers: portfolio task Phase 2,
  "map theses to tickers".
---

# Thesis → Vehicle Map (Track B Phase 2)

Bridge **`market_thesis_exploration`** to **tradable vehicles**. Multiple candidates per thesis are expected; this is **not** yet final sizing or a screener ranking.

---

## Inputs

1. **Published** `market_thesis_exploration` for `{{DATE}}` — `meta.source_exploration_key` in output must match its `document_key`.
2. **`config/investment-profile.md`** — risk, allowed asset classes, constraints, regime playbook.
3. **`config/preferences.md`** — style, themes the user cares about (mandate flavor, not weights).
4. **`config/watchlist.md`** — full ETF universe; candidates **must** be drawn from here unless `investment-profile` explicitly allows off-watchlist names (rare — document in `exclusion_reasons`).

**Do NOT read** `config/portfolio.json` **weights** in this step (tickers-only pull from watchlist is fine).

---

## Steps

### 1) One row per thesis

For each `thesis_id` from the exploration artifact, build a **`body.mappings[]`** entry:

- **`candidate_tickers[]`** — 1+ symbols from watchlist that could express the thesis (direct, hedge, or relative-value vehicles as appropriate).
- **`rationale`** — how each vehicle connects to thesis + regime (short).
- **`exclusion_reasons[]`** — notable watchlist names considered and rejected (optional but valuable).
- **`user_mandate_notes[]`** — how `investment-profile` / `preferences` constrained the set (e.g. no single-stock, max crypto sleeve).

### 2) Meta

- **`source_exploration_key`**: exact `document_key` of the exploration doc (e.g. `market-thesis-exploration/2026-04-11.json`).
- **`user_mandate_notes`**: session-level bullets (optional).

### 3) JSON artifact

- **`doc_type`**: `thesis_vehicle_map`, `schema_version`: `1.0`
- **Publish:** `thesis-vehicle-map/{{DATE}}.json`
- **Validate + publish** with `--doc-type-label "Thesis Vehicle Map"` and `--title "Thesis Vehicle Map"`

---

## Handoff

**[`skills/opportunity-screener/SKILL.md`](../opportunity-screener/SKILL.md)** uses this map as the **primary** input for building the analyst roster (plus digest/regime). If the map is missing, the screener falls back to legacy watchlist-only scoring.
