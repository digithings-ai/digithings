# Task: Deep Dive Research Note

**Before anything else:** read [`../PROJECT.md`](../PROJECT.md).

## Purpose

A deep dive is a long-form research note that provides comprehensive analysis on a topic that
warrants more than the daily pipeline's segment-level coverage. It is published to the Supabase
`documents` table under `research/deep-dives/` and surfaces in the Library under **Deep Dives**.

Deep dives are the primary mechanism for building the Obsidian Research Library — a curated
knowledge base of durable market, economic, and portfolio management insights that agents can
load as context in future sessions.

---

## When to produce a deep dive

A deep dive is warranted when:
- A **single ticker, sector, or theme** needs thesis-level conviction analysis (≥ 800 words)
- A **macro regime parallel** to a historical event (e.g., 1973 oil shock, 1994 rate shock, 2015 EM crisis) is relevant to current positioning
- A **structural concept** (factor investing, carry trade mechanics, commodity supercycles) needs a durable reference note
- The daily delta surface area is insufficient to capture the complexity of a developing situation
- The portfolio manager requests a deep dive before a large rebalance decision

---

## Document key naming

| Subject type | Key pattern | Example |
|---|---|---|
| Ticker analysis | `research/deep-dives/{TICKER}-{DATE}` | `research/deep-dives/NVDA-2026-04-14` |
| Sector / theme | `research/deep-dives/{SLUG}-{DATE}` | `research/deep-dives/ai-infrastructure-capex-2026-04` |
| Historical parallel | `research/deep-dives/parallel-{SLUG}-{DATE}` | `research/deep-dives/parallel-1973-oil-shock-2026-04` |
| Macro concept | `research/concepts/{SLUG}` | `research/concepts/carry-trade-mechanics` |
| Structural papers | `research/papers/{SLUG}` | `research/papers/macro-regime` |

---

## Markdown format (Obsidian-compatible)

Write in standard markdown with Obsidian extensions:

```markdown
# {Title}

> **Type:** Deep Dive | **Date:** {DATE} | **Ticker(s):** {TICKERS if any}
> **Tags:** #{tag1} #{tag2}
> **Related:** [[macro-regime]] [[factor-investing]]

## Summary
One-paragraph executive summary (max 150 words). State the key claim upfront.

## Context
What prompted this analysis. Reference the specific date and triggering event or question.

## Analysis
### {Sub-section 1}
...
### {Sub-section 2}
...

## Historical parallels
Compare to prior cycles. Use `[[wiki-link]]` to cross-reference existing papers.

## Portfolio implications
Direct positioning implications. How does this change the analyst's conviction on specific assets?

## Key risks
What would invalidate this thesis.

## References
- Source 1 (date accessed)
- Source 2 (date accessed)
```

**Obsidian wikilinks** (`[[topic]]`) are preserved in Supabase content and displayed in the Library.
Cross-link aggressively — the goal is a connected knowledge graph, not isolated notes.

---

## Publishing

### Option 1: From a file
```bash
python3 scripts/publish_research.py \
  --key research/deep-dives/NVDA-2026-04-14 \
  --title "NVDA Deep Dive — AI Infrastructure Capex Cycle" \
  --type deep-dive \
  --file /tmp/NVDA-2026-04-14.md \
  --date 2026-04-14 \
  --ticker NVDA \
  --tags ai semiconductor capex
```

### Option 2: Agent pipes markdown directly (no file needed)
```bash
# Agent writes markdown to stdout, pipes to publish script
python3 scripts/publish_research.py \
  --key research/deep-dives/{SLUG}-{DATE} \
  --title "{TITLE}" \
  --type deep-dive \
  --content - \
  --date {DATE}
# (then paste or pipe markdown)
```

### Option 3: List existing library
```bash
python3 scripts/publish_research.py --list
python3 scripts/fetch_research_library.py
python3 scripts/fetch_research_library.py --ticker NVDA
python3 scripts/fetch_research_library.py --type deep-dive
```

---

## Scope and depth targets

| Type | Word count | Sections | Cross-links |
|---|---|---|---|
| Ticker deep dive | 800–2,000 | 5–7 | ≥ 2 paper refs |
| Historical parallel | 1,000–2,500 | 6–8 | ≥ 3 paper refs |
| Macro concept | 600–1,500 | 4–6 | ≥ 1 paper ref |
| Structural paper | 1,500+ | 6–10 | Cite primary sources |

---

## Agent loading protocol

In any session that benefits from the research library, load context before analysis:

```bash
python3 scripts/fetch_research_library.py              # list all
python3 scripts/fetch_research_library.py --ticker IAU # gold-related notes
python3 scripts/fetch_research_library.py --type paper # doctrine papers only
```

The agent should cross-reference the library when:
1. Building a bull/bear case for an asset — cite the relevant paper's empirical findings
2. Classifying a macro regime — run the Ilmanen 4-quadrant check from `research/papers/macro-regime`
3. Sizing a position — reference the Black-Litterman and Kelly criterion from `research/papers/portfolio-construction`
4. Evaluating momentum signals — cite Antonacci / Faber from `research/papers/momentum-trend`

---

## Relationship to daily pipeline

Deep dives are **supplements**, not replacements, for the daily pipeline output. They are:
- Produced ad hoc when triggered (not on a fixed schedule)
- Stored permanently in Supabase (no expiry, unlike daily snapshots)
- Loaded into future agent sessions as background context
- Surfaced in the Library under **Deep Dives** or **Research Papers** tabs

The daily portfolio analyst (`deliberation-transcript`) should cite relevant deep dives when
conviction is derived from research beyond the current day's segment files.
