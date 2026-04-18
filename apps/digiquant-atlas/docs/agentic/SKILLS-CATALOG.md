# Skills catalog

**Authoritative list:** directories under [`skills/`](../../skills/) — each `skills/<slug>/SKILL.md` is one package. This page groups them for navigation; if it drifts, trust the filesystem.

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
| `orchestrator` | Full pipeline router |
| `weekly-baseline` | Sunday full baseline |
| `daily-delta` | Mon–Sat delta |
| `digest` | Phase 7 synthesis |
| `premarket-pulse` | Early session pulse |
| `monthly-synthesis` | Month-end rollup |
| `macro` | Phase 3 macro |
| `bonds` | 4A rates / credit |
| `commodities` | 4B |
| `forex` | 4C |
| `crypto` | 4D |
| `international` | 4E |
| `equity` | 5A US equities |
| `earnings` | Phase 6 |

---

## Sector packages (`sector-*`)

**11 GICS sector analysts:** `sector-technology`, `sector-healthcare`, `sector-financials`, `sector-energy`, `sector-consumer-disc`, `sector-consumer-staples`, `sector-industrials`, `sector-materials`, `sector-utilities`, `sector-real-estate`, `sector-comms`

**Cross-sector tools:** `sector-rotation`, `sector-heatmap`

---

## Alternative data (4)

`alt-sentiment-news`, `alt-cta-positioning`, `alt-options-derivatives`, `alt-politician-signals`

---

## Institutional (2)

`inst-institutional-flows`, `inst-hedge-fund-intel`

---

## Portfolio & research

| Slug | Role |
|------|------|
| `opportunity-screener` | Watchlist screen |
| `deliberation` | Multi-round PM prep |
| `portfolio-manager` | Sizing / rebalance |
| `asset-analyst` | Per-asset analyst |
| `thesis` | New thesis |
| `thesis-tracker` | Thesis scoring |
| `profile-setup` | Onboarding |
| `research-library` | Doctrine / citations |
| `research-daily` | **Track A** — blind research → publish `research_delta` with unique `research-delta/…` key |
| `deep-dive` | Ad-hoc ticker/topic |
| `github-workflow` | `gh` issues/PRs for pipeline evolution backlog |
| `sector-rotation` | Rotation themes |
| `sector-heatmap` | Heatmap |

---

## Data fetch (2)

| Slug | When to use |
|------|-------------|
| `data-fetch` | CLI / yfinance path; column references |
| `mcp-data-fetch` | Sandbox or when scripts fail — MCP tools |

---

## Package count

There are **46** skill directories on disk (`ls skills | wc -l`). The tables above group them by role; `sector-*` includes both GICS analysts and rotation/heatmap utilities.

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

See [`PROMPTS.md`](PROMPTS.md) “Adding a new skill” and [`WORKFLOWS.md`](WORKFLOWS.md).
