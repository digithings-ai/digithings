# Sector Analyst Agent

## Role

Sector-level research: relative strength, rotation, catalysts, and high-conviction names. Each GICS sector has a dedicated package: `skills/sector-<name>/SKILL.md`.

## Trigger phrases

- "Analyze {sector} sector", "{sector} deep dive", "Run sectors", "Sector rotation", "Sector heatmap"

## Inputs

- `config/watchlist.md`, `config/investment-profile.md`  
- Macro + market context from **Supabase** (`daily_snapshots`, `documents`) for the run date  

## Supported sectors (canonical paths)

| Sector | Skill package |
|--------|----------------|
| Technology | `skills/sector-technology/SKILL.md` |
| Healthcare | `skills/sector-healthcare/SKILL.md` |
| Financials | `skills/sector-financials/SKILL.md` |
| Energy | `skills/sector-energy/SKILL.md` |
| Consumer Discretionary | `skills/sector-consumer-disc/SKILL.md` |
| Consumer Staples | `skills/sector-consumer-staples/SKILL.md` |
| Industrials | `skills/sector-industrials/SKILL.md` |
| Materials | `skills/sector-materials/SKILL.md` |
| Utilities | `skills/sector-utilities/SKILL.md` |
| Real Estate | `skills/sector-real-estate/SKILL.md` |
| Communication Services | `skills/sector-comms/SKILL.md` |

## Workflow

1. Load the sector skill for the requested GICS bucket.  
2. Optional cross-sector reads: `skills/sector-rotation/SKILL.md`, `skills/sector-heatmap/SKILL.md`.  
3. Publish segment JSON per RUNBOOK.

## Outputs

Supabase `documents` rows for the sector segment — optional local markdown under `data/agent-cache/` is scratch only.
