---
name: portfolio-deliberation
description: >
  Multi-round analyst-PM deliberation. Per-ticker conference transcripts (fresh JSON each session),
  unbounded rounds until PM sets converged. Devil's advocate PM vs analysts; optional recess for
  light research. Triggers: "run deliberation", portfolio task Phase 5, Phase 7C orchestrator/delta.
---

# Portfolio Deliberation Skill

Structured **conference** between analyst (per ticker) and portfolio manager. Roles run sequentially; analysts commit outputs before the PM responds. **Thesis-first Track B** uses **one `deliberation_transcript` JSON per ticker** plus a **session index** document.

---

## Why Deliberation > One-Shot

| One-Shot (old) | Deliberation (new) |
|---|---|
| Analyst writes → PM reads → done | Analyst presents → PM challenges → Analyst defends → PM decides |
| Weak arguments pass unchallenged | PM forces specificity on every uncertain position |
| Anchoring to prior weights (subtle) | Explicit "what changed?" challenge catches stale reasoning |
| Disagreements hidden in boilerplate | Contradictions surfaced and resolved in transcript |

---

## Pre-Flight

Load all context per `skills/portfolio-manager/SKILL.md` Pre-Flight section:

- Macro regime (Supabase `daily_snapshots`)
- `config/preferences.md`, `config/investment-profile.md`
- `docs/research/LIBRARY.md`
- Digest (`documents` `digest`)
- **`research_changelog/{{DATE}}.json`** when present
- When available: **`market_thesis_exploration`**, **`thesis_vehicle_map`** for the date (ground debate in thesis IDs)

**Do NOT load `config/portfolio.json` weights** until the PM skill explicitly enters Phase C.

### Session identifiers

- Set **`meta.session_id`** (e.g. `{{DATE}}-pm` or a short UUID) on **every** per-ticker transcript and on the **session index**.
- Set **`meta.aggregate_index_document_key`** to `deliberation-transcript-index/{{DATE}}.json` on each per-ticker transcript.

### Weekday delta-scoped (`meta.kind: delta_scoped`)

Shorter roster (triggered tickers + at most 2 new candidates per `opportunity-screener` delta rules). Cite **`research_changelog`** when arguing from new information.

---

## Step 1 — Roster

Read the latest **opportunity screen** artifact (Supabase `documents`): holdings (tickers only) + candidates.

Fallback: `portfolio.json` tickers only; no candidates unless screener run.

---

## Step 2 — Per-ticker conferences (publish order)

For **each** ticker on the roster **in sequence**:

### 2.1 Round 1 — Presentation

- If a published **`asset_recommendation`** exists for this ticker and date, **summarize it** as Round 1 in `body.rounds` (do not rerun `skills/asset-analyst/SKILL.md` unless the PM marks it stale).
- Otherwise run `skills/asset-analyst/SKILL.md` first, publish JSON, then summarize.

### 2.2 Further rounds — PM challenge ↔ analyst response

Repeat until **`meta.converged: true`** for this ticker:

- PM may **challenge** (use trigger table below), **request recess for research**, or **accept** the current recommendation.
- Analyst responds with **Defend / Revise / Concede** (same rules as before); on recess, analyst performs **limited** targeted research, **republishes** `asset_recommendation` with `meta.light_research_requested`, then continues the transcript in a new `body.rounds[]` entry labeled e.g. `Round N — Post-recess`.

**No fixed maximum rounds** — terminate only when the PM sets **`meta.converged: true`** or explicitly **escalates** to the user (note in `body.footer_notes`).

### Challenge triggers (PM MUST challenge when applicable)

| # | Trigger | PM Challenge Framing |
|---|---------|---------------------|
| 1 | **Analyst bias = "Conflicted"** | "Pick a direction. What single data point would resolve your uncertainty?" |
| 2 | **Both bull AND bear conviction are Medium or Low** | "What's the actual signal — or is this a skip?" |
| 3 | **Weight > 0% but thesis is ⚠️ or ❌** | "Defend capital in a damaged thesis or cut to 0%." |
| 4 | **Rec weight contradicts macro regime** | "Reconcile with regime or revise." |
| 5 | **Cross-ticker contradiction** | Surface explicit conflict with another symbol's assumptions. |
| 6 | **Exit condition vague** | Demand measurable exit. |
| 7 | **Recycling prior session with no new evidence** | "What changed today?" |

### 2.3 Final row for this ticker

Append to **`body.final_decisions`** at least one object for this **`ticker`** with `analyst_recommendation`, `pm_decision`, `invalidation_condition`.

### 2.4 Transcript JSON format (CRITICAL — must match schema exactly)

The per-ticker transcript payload **must** validate against `templates/schemas/deliberation-transcript.schema.json`. The schema enforces `additionalProperties: false` — extra fields cause validation failure.

**Required top-level envelope:**

```json
{
  "schema_version": "1.0",
  "doc_type": "deliberation_transcript",
  "date": "{{DATE}}",
  "meta": {
    "kind": "delta_scoped",
    "session_id": "{{DATE}}-pm",
    "related_ticker": "{{TICKER}}",
    "converged": true,
    "aggregate_index_document_key": "deliberation-transcript-index/{{DATE}}.json"
  },
  "body": {
    "trigger_summary": ["One sentence describing why this ticker was deliberated."],
    "rounds": [...],
    "final_decisions": [...],
    "thesis_updates": [...]
  }
}
```

**`body.rounds` format — each round is `{label, sections[{heading, markdown}]}`:**

```json
"rounds": [
  {
    "label": "Round 1 — Analyst Presentation",
    "sections": [
      {
        "heading": "Analyst",
        "markdown": "Full analyst presentation text here..."
      },
      {
        "heading": "PM Challenge",
        "markdown": "PM challenge text here..."
      }
    ]
  },
  {
    "label": "Round 2 — Defense",
    "sections": [
      {
        "heading": "Analyst Response",
        "markdown": "Defense / revision text..."
      },
      {
        "heading": "PM Decision",
        "markdown": "Accepted / rejected with reasoning..."
      }
    ]
  }
]
```

**NEVER use this shape** (wrong — old chat format, UI will render empty dropdowns):
```json
{ "pm": "...", "analyst": "...", "round": 1 }
```

**`body.trigger_summary`** — must be an **array of strings**, NOT a single string:
```json
"trigger_summary": ["BIL held at 55%; analyst recommends reduction to 20% given risk-on signals."]
```

**`body.final_decisions`** — allowed fields only (`ticker`, `analyst_recommendation`, `pm_decision`, `invalidation_condition`). Do not add `action` or other fields:
```json
"final_decisions": [
  {
    "ticker": "{{TICKER}}",
    "analyst_recommendation": "20% HOLD",
    "pm_decision": "20% HOLD — accepted",
    "invalidation_condition": "Restore to 35% if VIX > 35 or Iran talks fail"
  }
]
```

**`body.thesis_updates`** — use `status` (not `prior_status`/`updated_status`):
```json
"thesis_updates": [
  {
    "thesis_id": "T-002",
    "status": "active",
    "note": "BIL position reduced; thesis intact."
  }
]
```

### 2.5 Publish per-ticker transcript

```bash
# Validate first — fail fast rather than publish invalid payloads
python3 scripts/validate_artifact.py - <<'EOF'
{ ... transcript JSON ... }
EOF

python3 scripts/publish_document.py \
  --payload - \
  --document-key "deliberation-transcript/{{DATE}}/{{TICKER}}.json" \
  --title "{{TICKER}}" \
  --doc-type-label "Deliberation Transcript"

# title MUST be the ticker symbol only (e.g. "NVDA").
# The UI groups deliberation and recommendation under a per-ticker section automatically.
```

---

## Step 3 — Session index (fresh)

Publish **`deliberation_session_index`** (`templates/schemas/deliberation-session-index.schema.json`).

**Required envelope (top-level `schema_version`, `doc_type`, `date` are mandatory):**

```json
{
  "schema_version": "1.0",
  "doc_type": "deliberation_session_index",
  "date": "{{DATE}}",
  "meta": {
    "session_id": "{{DATE}}-pm",
    "kind": "delta_scoped",
    "all_converged": true
  },
  "body": {
    "entries": [
      {
        "ticker": "BIL",
        "document_key": "deliberation-transcript/{{DATE}}/BIL.json",
        "converged": true,
        "rounds_completed": 2
      }
    ]
  }
}
```

**Allowed entry fields only:** `ticker`, `document_key`, `converged`, `rounds_completed`. Do not add `action`, `pm_decision_weight`, or other fields.

```bash
python3 scripts/validate_artifact.py - <<'EOF'
{ ... session index JSON ... }
EOF

python3 scripts/publish_document.py \
  --payload - \
  --document-key "deliberation-transcript-index/{{DATE}}.json" \
  --title "Deliberation Session Index — {{DATE}}" \
  --doc-type-label "Deliberation Session Index"
```

---

## Cross-ticker conflicts

If Round N for ticker A exposes a contradiction with ticker B, the PM **adds a round** on **both** transcripts (or a linked note in the session index `footer_notes`) so the conflict is explicit before `skills/portfolio-manager/SKILL.md` runs.

---

## Integration

- **Orchestrator Phase 7C** / **daily-delta Phase 7C–7D:** same protocol; scoped roster on weekdays.
- **Portfolio task:** runs after **Phase 4** analyst publishes; **before** **`pm_allocation_memo`** and PM clean-slate.

---

## Handoff

`skills/portfolio-manager/SKILL.md` **ingests** all per-ticker transcripts + session index (+ **`pm_allocation_memo`** when published) to build the clean-slate portfolio.

---

## Quality Standards

1. **PM challenges must be specific**
2. **Defenses must cite data** (session payloads, changelog, or recess research)
3. **Concessions are valuable**
4. **Escalate honestly**
5. **Contradictions are surfaced**, not hidden
