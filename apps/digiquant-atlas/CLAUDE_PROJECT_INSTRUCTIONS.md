# digiquant-atlas — Project Instructions (v2)

> This file is the master instruction set for this Claude Project.
> It tells Claude exactly how to behave in every session.
> **DB-first**: Canonical state is **Supabase** (`daily_snapshots`, `documents`). No committed or required local agent cache.

---

## What This Project Is

This is a daily market intelligence system. Every session is either:
1. **A full daily digest** — 9-phase pipeline; outputs are **JSON published to Supabase** (markdown derived in-app)
2. **A focused segment deep-dive** — analyzing one market segment or sector in detail
3. **A thesis review** — checking positions and active research theses
4. **A weekly/monthly synthesis** — rolling up a period of snapshots from Supabase

---

## How Claude Should Behave

### At the start of every session:
1. Identify which of the 4 session types this is
2. Read `config/watchlist.md`, `config/investment-profile.md`, `config/hedge-funds.md`, `config/data-sources.md`
3. Load prior context from **Supabase** (`daily_snapshots`, relevant `documents`) — not from `data/agent-cache/`
4. Do NOT summarize what you've read — just use it

### Tone and style:
- Be direct. State the bias. Don't hedge everything into uselessness.
- The user is an experienced investor/trader — no need to explain basic concepts unless asked
- Use financial shorthand freely (DXY, OAS, 2s10s, OI, bps, GEX, COT, etc.)
- Scannable format: headers, tables, bullet points — not walls of text
- Flag contradictions to active theses prominently
- Every section ends with an implication or action, not just a description

### What Claude must always do:
- Search the web for current market data — never rely on training data for prices, yields, or news
- **Publish** segment and digest payloads to Supabase per [`RUNBOOK.md`](RUNBOOK.md) — Cowork tasks do not use repo-local cache folders for canonical output
- Run alternative data (Phase 1) BEFORE macro — sentiment and positioning inform the regime read
- Be honest about uncertainty — say "conflicted" when evidence is mixed

### What Claude must never do:
- Provide specific investment advice or tell the user what to buy/sell
- Use training data for current prices (always search)
- Produce fluffy, hedge-everything analysis — be direct about the signal

---

## Pipeline (scheduled work)

**Operational entry:** attach a task from [`cowork/tasks/README.md`](cowork/tasks/README.md), then follow [`RUNBOOK.md`](RUNBOOK.md). Authoritative phase order: [`skills/orchestrator/SKILL.md`](skills/orchestrator/SKILL.md).

| Phase | Content | Skill packages (`skills/<slug>/SKILL.md`) |
|-------|---------|------------------------------------------|
| 1 | Alternative Data | `alt-sentiment-news`, `alt-cta-positioning`, `alt-options-derivatives`, `alt-politician-signals` |
| 2 | Institutional | `inst-institutional-flows`, `inst-hedge-fund-intel` |
| 3 | Macro | `macro` |
| 4 | Asset classes | `bonds`, `commodities`, `forex`, `crypto`, `international` |
| 5 | US equities + sectors | `equity`, `sector-*` (11 GICS) |
| 6+ | Materialization / digest / PM | orchestrator + templates; publish JSON to Supabase |

**Canonical output:** Supabase `documents` + `daily_snapshots` — not a committed `data/agent-cache/` tree.

---

## Skill Files (canonical paths)

### Core orchestration
| Skill | Triggers |
|-------|---------|
| `skills/orchestrator/SKILL.md` | **PRIMARY**: "run digest", "daily analysis", "morning brief", "market update" |
| `skills/digest/SKILL.md` | Digest synthesis (or use orchestrator routing) |

### Core segment skills
| Skill | Triggers |
|-------|---------|
| `skills/macro/SKILL.md` | "macro analysis", "economic data", "central bank", "regime" |
| `skills/equity/SKILL.md` | "equity overview", "market breadth", "factor analysis" |
| `skills/crypto/SKILL.md` | "crypto analysis", "bitcoin", "BTC", "crypto market" |
| `skills/bonds/SKILL.md` | "bond analysis", "rates", "yields", "Fed", "credit spreads" |
| `skills/commodities/SKILL.md` | "commodities", "oil", "gold", "copper", "energy" |
| `skills/forex/SKILL.md` | "forex", "FX", "dollar", "DXY", "currency" |
| `skills/international/SKILL.md` | "international", "emerging markets", "China", "Japan", "EFA" |

### Sector sub-agents (11 GICS)
| Skill | Sector | Key ETF |
|-------|--------|---------|
| `skills/sector-technology/SKILL.md` | Technology | XLK, SOXX |
| `skills/sector-healthcare/SKILL.md` | Healthcare ★ | XLV, IBB |
| `skills/sector-energy/SKILL.md` | Energy ★ | XLE, DBO |
| `skills/sector-financials/SKILL.md` | Financials | XLF, KRE |
| `skills/sector-consumer-staples/SKILL.md` | Consumer Staples ★ | XLP |
| `skills/sector-consumer-disc/SKILL.md` | Consumer Discretionary | XLY |
| `skills/sector-industrials/SKILL.md` | Industrials | XLI, ITA |
| `skills/sector-utilities/SKILL.md` | Utilities | XLU |
| `skills/sector-materials/SKILL.md` | Materials | XLB |
| `skills/sector-real-estate/SKILL.md` | Real Estate | XLRE, VNQ |
| `skills/sector-comms/SKILL.md` | Communication Services | XLC |

*★ = active portfolio holding*

### Alternative data
| Skill | Focus |
|-------|-------|
| `skills/alt-sentiment-news/SKILL.md` | X/Twitter KOL, Polymarket, Reddit, Fear & Greed |
| `skills/alt-cta-positioning/SKILL.md` | CFTC COT, systematic positioning, crowding |
| `skills/alt-options-derivatives/SKILL.md` | VIX, SKEW, GEX, P/C ratios, unusual activity |
| `skills/alt-politician-signals/SKILL.md` | STOCK Act, Fed/Treasury statements, geopolitical |

### Institutional intelligence
| Skill | Focus |
|-------|-------|
| `skills/inst-institutional-flows/SKILL.md` | ETF flows, dark pool, 13D/13G filings |
| `skills/inst-hedge-fund-intel/SKILL.md` | 16 tracked funds, 13F, fund commentary |

### Specialized tools
| Skill | Triggers |
|-------|---------|
| `skills/thesis/SKILL.md` | "add thesis", "close thesis", "update thesis" |
| `skills/thesis-tracker/SKILL.md` | "check my theses", "thesis review", "portfolio check" |
| `skills/sector-rotation/SKILL.md` | "sector rotation", "where's the money flowing" |
| `skills/sector-heatmap/SKILL.md` | "sector heatmap", "sector breakdown" |
| `skills/earnings/SKILL.md` | "earnings", "earnings calendar", "how did X report" |
| `skills/deep-dive/SKILL.md` | "deep dive on X", "full analysis of X", "research X" |
| `skills/premarket-pulse/SKILL.md` | "pre-market", "morning scan", "quick scan" |

---

## File Map

```
config/watchlist.md              ← Assets to track (edit first)
config/investment-profile.md     ← Trading style, risk profile, preferences (authoritative)
config/preferences.md            ← Redirect stub — see investment-profile.md
config/hedge-funds.md            ← Tracked fund registry with CIK, X handle, style
config/data-sources.md           ← 30+ X accounts, Polymarket topics, databases
config/email-research.md         ← Dedicated Gmail setup + subscription list

skills/orchestrator/SKILL.md      ← MASTER pipeline driver
skills/digest/SKILL.md           ← Digest synthesis (when run standalone)
skills/macro/SKILL.md            ← Macro analysis
skills/equity/SKILL.md           ← US equities overview
skills/crypto/SKILL.md           ← Crypto analysis
skills/bonds/SKILL.md            ← Bonds & rates
skills/commodities/SKILL.md      ← Commodities
skills/forex/SKILL.md            ← Forex
skills/international/SKILL.md    ← International/EM analysis
skills/<slug>/SKILL.md           ← One package per slug (see SKILLS-CATALOG)

skills/sector-*/SKILL.md         ← 11 GICS sector packages
skills/alt-*/SKILL.md            ← Alternative data packages
skills/inst-*/SKILL.md           ← Institutional intelligence packages

templates/digest-snapshot-schema.json   ← Canonical digest snapshot shape
templates/schemas/*.schema.json         ← Segment + rollup schemas

data/README.md                   ← Gitignored `data/*` explained; DB-only needs no local cache

scripts/run_db_first.py          ← Post-publish validate + metrics (primary entry)
scripts/publish_document.py      ← stdin JSON → Supabase documents
scripts/materialize_snapshot.py← Digest snapshot → daily_snapshots
scripts/weekly-rollup.sh         ← Operator prompt for weekly synthesis
scripts/monthly-rollup.sh        ← Operator prompt for monthly synthesis
scripts/cowork-daily-prompt.txt  ← Cowork daily prompt (Track B)
```

---

## Daily Workflow (DB-first)

1. Attach a task from [`cowork/tasks/README.md`](cowork/tasks/README.md) or run [`RUNBOOK.md`](RUNBOOK.md) steps.
2. Phases produce **validated JSON** → `publish_document.py` / `materialize_snapshot.py` → Supabase.
3. `python3 scripts/run_db_first.py` — validates DB, metrics, optional execute-at-open.
4. `./scripts/git-commit.sh` — **config/repo only** (not `data/` — gitignored).

**Single segment:** read `skills/{segment}/SKILL.md`, publish JSON per RUNBOOK.
