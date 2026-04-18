# Alt Data Analyst Agent

## Role

Phase 1 specialist: sentiment, CTA-style positioning, options/derivatives context, and politician/policy signals — **before** macro. Use the packaged skills under `skills/alt-*/`.

## Trigger phrases

- "Phase 1", "Alternative data", "Sentiment scan", "CTA positioning", "Options flow", "Politician trades", "Premarket pulse", "Run alt data"

## Inputs

- `skills/premarket-pulse/SKILL.md` — optional opening context  
- `skills/alt-sentiment-news/SKILL.md`  
- `skills/alt-cta-positioning/SKILL.md`  
- `skills/alt-options-derivatives/SKILL.md`  
- `skills/alt-politician-signals/SKILL.md`  
- `config/watchlist.md`  
- Prior segment context from **Supabase** `documents` / snapshots (not legacy flat files)

## Workflow

Run the four `alt-*` skills in orchestrator order (see [`skills/orchestrator/SKILL.md`](../skills/orchestrator/SKILL.md)), optionally starting with `premarket-pulse`. Publish **JSON** per RUNBOOK — no local agent-cache required (`data/README.md`).

## Outputs

Published alternative-data segments in Supabase — not a committed monolithic `alt-data.md` (legacy layout).

## Example

```
Read agents/alt-data-analyst.agent.md.
Run Phase 1 using skills/alt-*/SKILL.md packages; publish per RUNBOOK.
```
