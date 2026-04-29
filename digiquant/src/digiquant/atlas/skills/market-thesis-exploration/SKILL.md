---
name: market-thesis-exploration
description: >
  Track B Phase 1 — synthesize market-facing theses from Supabase research only. No portfolio weights,
  no preferences or investment-profile. Produces market_thesis_exploration JSON. Triggers: portfolio
  task Phase 1, "explore market theses from today's research".
---

# Market Thesis Exploration (Track B Phase 1)

Turn **compiled research** into **exploratory market theses**: opportunities, trends, headwinds/tailwinds, bull/bear sketches, sub-theses, and explicit **validation / invalidation** criteria. Style is hedge-fund-like **idea generation** — not yet mandate-constrained and not necessarily actionable as trades.

---

## Hard rules (blinding)

**Do NOT read:** `config/portfolio.json`, `config/preferences.md`, `config/investment-profile.md`.

**May read (optional universe only):** `config/watchlist.md` — ticker **names and categories** to keep vehicle ideas realistic; never infer holdings or weights.

---

## Inputs (DB-first)

1. **`daily_snapshots`** for `{{DATE}}` — regime, `segment_biases`, key levels.
2. **`documents`** — `digest` payload; any `research-delta/…` for the date; `research-changelog/{{DATE}}.json` if present; `research_baseline_manifest` if present.
3. Prior **market thesis exploration** for the same week (same `baseline_date` / week anchor) if published — use as **carry-forward** base; apply **deltas** via new full JSON or `document_delta` targeting this doc (operator choice).

The **`digest`** is **input only** here — it must already exist from the **research** task ([`cowork/tasks/research-weekly-baseline.md`](../../cowork/tasks/research-weekly-baseline.md) / [`cowork/tasks/research-daily-delta.md`](../../cowork/tasks/research-daily-delta.md)); Track B does not compile it.

Announce: "Market thesis exploration — research-only context loaded."

---

## Steps

### 1) Executive pointer

Write a short **overview** (`body.executive_digest_pointer`) that orients the reader: regime, largest movers, what stayed stable. Point to digest paths or segment names — do not paste the entire digest.

### 2) Optional deeper dives

Add `body.deeper_dives[]` strings for 1–3 themes that deserve more narrative (still research-grounded).

### 3) Thesis register (core)

For each thesis in `body.theses[]`:

- **`thesis_id`**: stable ID for the week (e.g. `MT-001`) — align with later **vehicle map** rows.
- **Direction / statement** — clear view; can be multi-horizon.
- **`sub_theses`** — optional nested claims with their own validate/invalidate lines.
- **`validation_criteria` / `invalidation_criteria`** — measurable, time-bound where possible (prices, spreads, policy events, data prints).
- **`headwinds` / `tailwinds` / `bull_case` / `bear_case`** — exploratory, not a court trial; surface asymmetry.
- **`linked_research_refs`** — cite `document_key`, changelog lines, or snapshot paths.

### 4) JSON artifact

Emit **`doc_type`: `market_thesis_exploration`**, `schema_version`: `1.0`, `date`: `{{DATE}}`.

- **Publish:** `document_key` e.g. `market-thesis-exploration/{{DATE}}.json`
- **Validate:** `python3 scripts/validate_artifact.py - < payload.json`
- **Publish to Supabase:** `python3 scripts/publish_document.py --payload - --document-key market-thesis-exploration/{{DATE}}.json --title "Thesis Exploration" --doc-type-label "Market Thesis Exploration"`

---

## Quality bar

1. **Specific invalidation** — "if X then thesis weakens" beats "if things change".
2. **Sub-theses** when a theme has independent legs (e.g. commodity vs equity expression).
3. **Every thesis** ties to at least one `linked_research_refs` entry.
4. **No portfolio language** — no "we should own", no weights, no "trim/add" for the user book.

---

## Integration

Called from [`cowork/tasks/portfolio-pm-rebalance.md`](../../cowork/tasks/portfolio-pm-rebalance.md) **before** [`skills/thesis-vehicle-map/SKILL.md`](../thesis-vehicle-map/SKILL.md).
