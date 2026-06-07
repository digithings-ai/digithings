---
name: asset-analyst
description: >
  Per-asset conviction builder. Run once per portfolio position (or candidate position) to produce
  a structured bull/bear/conviction/weight recommendation BLINDED to current portfolio weights.
  Triggers when portfolio-manager calls for an analyst pass, or standalone for ad-hoc
  asset deep-dives: "analyze IAU", "bull/bear on XLE", "should I hold BIL".
---

# Asset Analyst Skill

This skill produces a structured per-asset recommendation.

## Critical Rule — Portfolio Blindness

**You MUST NOT read `config/portfolio.json` during this skill.**
**You MUST NOT reference current portfolio weights, current holdings, or position sizes.**

The analyst's job is to form an independent view on the asset's merit — unconstrained by what
is already owned. Anchoring to existing positions produces stale, sticky portfolios. The portfolio
manager (Phase B/C of `skills/portfolio-manager/SKILL.md`) handles the comparison — not this analyst.

---

## Inputs

1. **Ticker and category** — provided by the PM agent that invoked this skill
2. **Session segment files** — already produced earlier in the current session. Pull data FROM THESE FILES rather than initiating new web searches (data was already gathered in Phases 1–5). Relevant sources:
   - **DB-first**: use Supabase `daily_snapshots.snapshot` + relevant `documents.payload` artifacts for the same date.
3. **Market thesis linkage (Track B)** — load published **`market_thesis_exploration`** and **`thesis_vehicle_map`** for the date when present. Set JSON **`meta.linked_thesis_ids`** to every `thesis_id` that this ticker expresses (from the vehicle map row(s)). Set **`meta.research_citations`** to concrete refs (`document_key`, `changelog_item`, or digest path strings) supporting the view.
4. **Active theses** — note which thesis IDs are relevant; prefer **`linked_thesis_ids`** over legacy single **`meta.thesis_id`** when both apply.
5. **Macro regime** — from Supabase `daily_snapshots.regime` / `daily_snapshots.segment_biases`
6. **Research library** — `docs/research/LIBRARY.md`. Load once per session before forming bull/bear arguments. Cite at least one paper per argument. Use the Quick Reference tables (bottom) for per-asset signal rules. For macro regime framing, apply the Ilmanen 4-quadrant model (Section 5.4).

---

## Steps

### Step 1: Load Asset Context
Read the relevant segment file(s) from the list above. Extract:
- Current price / level
- Most recent bias for this asset stated in the segment file
- Key data points (yield, price move, volume, flow direction, etc.)
- Any relevant thesis confirmation or challenge signal

**Do NOT initiate new web searches.** If data is missing from segment files, note the gap
and work with what is available.

### Step 2: Build the Bull Case
Construct exactly 3 bull case arguments, each grounded in a specific data point from Step 1:
- Each argument must be falsifiable (i.e., it can be proven wrong)
- Order from strongest to weakest conviction
- Reference the macro regime where relevant (e.g., "In a risk-off / inflation regime, gold benefits from...")

### Step 3: Build the Bear Case
Construct exactly 3 bear case arguments, each with a specific counter-signal or risk:
- Include the thesis invalidation condition if one exists in the current digest Thesis Tracker
- Be honest — if the bull case is overwhelming, the bear case still needs to be real risks, not strawmen

### Step 4: Form the Analyst Verdict
State a single base bias: Bullish / Bearish / Neutral / Conflicted

Assess the relevant thesis:
- ✅ Confirmed — data from today reinforces the thesis
- ⚠️ Conflicted — mixed signals; thesis not yet broken but challenged
- ❌ Challenged — today's data is clearly inconsistent with the thesis
- ⏳ No signal — insufficient new data to update the thesis

State specific entry and exit conditions for this asset.

### Step 5: Recommend a Weight
Use ONLY these quantized values: **0% / 5% / 10% / 15% / 20%**

Apply these reasoning rules:
- **0%** — Bearish OR thesis challenged OR macro regime is directly opposed. No position.
- **5%** — Weak positive signal OR conflicted thesis OR regime-neutral, used for diversification
- **10%** — Moderate conviction, thesis confirmed, regime supportive
- **15%** — High conviction, clear thesis confirmation, regime strongly supportive
- **20%** — Maximum single-asset conviction: thesis fully confirmed, regime aligned, institutional flows supporting, strong signal confluence. Reserve for 1–2 assets maximum per portfolio.

Justify the weight choice in 1-2 sentences. Do not default to the current weight — form the recommendation independently.

### Step 6: Write Output
Write the completed report as **JSON** (schema: `templates/schemas/asset-recommendation.schema.json`).
Save to: `data/agent-cache/daily/{{DATE}}/positions/{{TICKER}}.json` (optional local scratch), then **validate and publish** to Supabase:

```bash
python3 scripts/validate_artifact.py - < positions/{{TICKER}}.json
python3 scripts/publish_document.py --payload - --document-key asset-recommendations/{{DATE}}/{{TICKER}}.json --title "{{TICKER}}" --doc-type-label "Asset Recommendation"
# title MUST be the ticker symbol only (e.g. "NVDA"). The UI groups recommendations under the per-ticker section automatically.
```

Create the `positions/` subdirectory if it doesn't exist.

---

## Round 2 — PM Challenge Response (If Called Back)

If the PM challenges this analyst's position during deliberation (see `skills/deliberation/SKILL.md`),
add a response block to the relevant **per-ticker** deliberation transcript round, and update the analyst JSON payload if needed.

**Recess for research:** When the PM requests more evidence, set **`meta.light_research_requested`: true** on the revised `asset_recommendation`, perform **limited** targeted lookup (narrow queries only), then republish the JSON before the next deliberation round.

Response rules:
- **Defend**: Must cite a specific data point from session outputs NOT used in Round 1. If no new evidence exists, cannot Defend — must Revise or Concede.
- **Revise**: Adjust weight, bias, or thesis status. Explain what the PM's challenge exposed.
- **Concede**: Agree the position lacks support. Reduce weight to 0% or next lower tier.

---

## Token Efficiency Note

This skill deliberately pulls from already-gathered phase outputs rather than re-searching the web.
Running analysts for 7 portfolio positions adds approximately 5–10% additional context vs re-searching
would add 50–100%. Always use session files as the primary source.

---

## Output Format

See `templates/schemas/asset-recommendation.schema.json` for the complete output structure.

Key fields per output:
- Bull Case × 3 with data points
- Bear Case × 3 with specific risks
- Base Bias (single label)
- Thesis Status (per thesis ID)
- Recommended Weight (quantized: 0/5/10/15/20%)
- Theme Bucket (for PM aggregation)
- Entry/exit conditions
- Round 2 PM Challenge Response (if deliberation is active)

