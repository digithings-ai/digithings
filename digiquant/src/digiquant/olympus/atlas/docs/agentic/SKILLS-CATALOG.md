# Skills catalog

> **Graph-loaded skills only.** This catalog lists skills that are wired into the Atlas/Hermes LangGraph pipeline. Retired human-session wrappers (orchestrator, daily-delta, weekly-baseline, premarket-pulse, data-fetch, mcp-data-fetch, earnings, sector-rotation, sector-heatmap, asset-analyst, profile-setup, research-library, research-daily, deep-dive, github-workflow, market-thesis-exploration, opportunity-screener, deliberation, thesis, thesis-tracker, thesis-vehicle-map) have been removed. If this page drifts, the filesystem is authoritative: `ls skills/ | wc -l`.

---

## How skill files work

1. YAML frontmatter: `name:` (routing key), `description:`
2. Numbered steps for the agent
3. Output paths using `{{DATE}}` where applicable
4. `## Memory Update` when a ROLLING.md is appended

---

## Pipeline & core segments

| Slug | Role |
|------|------|
| `digest` | Phase 7 synthesis |
| `monthly-synthesis` | Month-end rollup |
| `macro` | Phase 3 macro |
| `bonds` | 4A rates / credit |
| `commodities` | 4B |
| `forex` | 4C |
| `crypto` | 4D |
| `international` | 4E |
| `equity` | 5A US equities |

---

## Sector packages (`sector-*`)

**11 GICS sector analysts:** `sector-technology`, `sector-healthcare`, `sector-financials`, `sector-energy`, `sector-consumer-disc`, `sector-consumer-staples`, `sector-industrials`, `sector-materials`, `sector-utilities`, `sector-real-estate`, `sector-comms`

---

## Alternative data (4)

`alt-sentiment-news`, `alt-cta-positioning`, `alt-options-derivatives`, `alt-politician-signals`

---

## Institutional (2)

`inst-institutional-flows`, `inst-hedge-fund-intel`

---

## Portfolio & AI signals

`alt-ai-portfolios`, `alt-politician-signals`

---

## Decision & reflection

| Slug | Role |
|------|------|
| `decision-reflector` | Post-decision review |
| `pipeline-evolution` | Pipeline improvement tracking |

---

## Hermes skills

| Slug | Role |
|------|------|
| `technical-analyst` | Technical analysis |
| `sentiment-analyst` | Sentiment analysis |
| `news-analyst` | News analysis |
| `fundamental-analyst` | Fundamental analysis |
| `research-debate` | Multi-analyst debate round |
| `research-manager` | Research coordination |
| `risk-aggressive` | Aggressive risk profile |
| `risk-conservative` | Conservative risk profile |
| `pm-rebalance-decision` | PM rebalance decision |
| `portfolio-manager` | Sizing / rebalance |
| `pm-allocation-memo` | Allocation memo output |

---

## Package count

The filesystem is authoritative: `ls skills/ | wc -l`. Retired non-graph skills have been removed; the tables above reflect graph-loaded skills only.

---

## Skill file template

When adding a skill:

```markdown
---
name: skill-identifier
description: One-line description
---

## Purpose
...

### 1. ...
```

See [`PROMPTS.md`](PROMPTS.md) "Adding a new skill" and [`WORKFLOWS.md`](WORKFLOWS.md).
