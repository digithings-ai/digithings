---
name: research-library
description: >
  Load curated research from the two-tier research library. Tier 1: doctrine papers and
  dynamic deep dives in Supabase under research/papers/ and research/deep-dives/.
  Tier 2: quick-reference summary in docs/research/LIBRARY.md (load first for fast context).
  Use when the portfolio manager, asset analyst, or orchestrator needs evidence-based
  allocation rules or prior deep-dive research.
  Triggers: "research library", "paper notes", "tactical allocation doctrine", "cite research",
  "what do we know about", "prior research on".
---

# Research Library

Two-tier knowledge base. Load only what the current task needs.

---

## Tier 1 — Quick-Reference Summary (git-tracked)

`docs/research/LIBRARY.md` — 575-line condensed index of all doctrine papers with
Quick Reference tables, per-asset decision rules, and agent loading instructions.
**Always load this first.** It is the fastest path to citable allocation rules.

---

## Tier 2 — Full Papers + Deep Dives (Supabase)

All papers and deep dives live in the `documents` table under `research/` keys.

**document_key patterns:**
- `research/papers/{SLUG}` — static doctrine papers (7 papers uploaded 2026-04-05)
- `research/deep-dives/{TICKER}-{DATE}` — single-asset or theme deep dives
- `research/concepts/{SLUG}` — timeless frameworks and concepts
- `research/themes/{SLUG}-{DATE}` — market theme analyses

**Load index:**
```bash
python3 scripts/fetch_research_library.py
```

**Fetch a specific note:**
```bash
python3 scripts/fetch_research_library.py --key research/deep-dives/NVDA-2026-04-14
```

**Filter by ticker or type:**
```bash
python3 scripts/fetch_research_library.py --ticker NVDA
python3 scripts/fetch_research_library.py --type concept
```

**Cache all to local scratch (optional session preload):**
```bash
python3 scripts/fetch_research_library.py --cache data/agent-cache/research/
```

---

## Output contract

- State **which sources** you used (Tier 1 path or Tier 2 document_key).
- Extract **2–5 actionable rules** (bullets) with section references where possible.
- State **how** they apply to today's allocation or thesis — not generic prose.

## Token discipline

Do **not** paste entire papers or notes. Summarize decision rules only.
