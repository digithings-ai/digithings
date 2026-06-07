---
name: market-thesis
description: >
  Manage, review, and evolve active market theses. Use this skill when the user says
  "review my theses", "update thesis", "add a new thesis", "close a thesis", "thesis tracker",
  "what are my current bets", or "how are my theses holding up". Also triggered at the end of
  each weekly rollup. 
---

# Thesis Management Skill

The thesis register is the core of the research system. Every meaningful market view should be
captured here with an entry date, rationale, supporting evidence, and eventual resolution.

---

## Thesis Register Location

DB-first: store theses in Supabase (`theses` table) and/or as structured `documents.payload` artifacts.
Config files (e.g. `config/preferences.md`) reflect the currently active themes the user cares about.

---

## Thesis Structure

Each thesis has these fields:

```markdown
### [THESIS-ID] [Short Title]
- **Status**: ACTIVE / CONFIRMED / CHALLENGED / CLOSED-WIN / CLOSED-LOSS / EXPIRED
- **Opened**: YYYY-MM-DD
- **Closed**: YYYY-MM-DD (if applicable)
- **Time Horizon**: [days / weeks / months]
- **Asset(s)**: [ticker, sector, asset class]
- **Direction**: [Long / Short / Neutral / Relative value]
- **Thesis**: [2-4 sentence statement of the view and why]
- **Entry Catalyst**: [What triggered opening this thesis]
- **Invalidation**: [What would prove this thesis wrong — be specific]
- **Supporting Evidence**: (appended over time)
  - YYYY-MM-DD: [evidence point]
  - YYYY-MM-DD: [evidence point]
- **Contradicting Evidence**: (appended over time)
  - YYYY-MM-DD: [counter-evidence]
- **Resolution**: [How it closed and what was learned] (if closed)
```

---

## Operations

### Adding a New Thesis
When the user says "add thesis" or a new view emerges from a digest:
1. Assign ID: T-XXX (increment from last)
2. Fill all fields — be specific about invalidation
3. Add a one-liner to `config/preferences.md` under "Current Portfolio Themes"

### Updating a Thesis
When evidence accumulates:
1. Append to "Supporting Evidence" or "Contradicting Evidence" with date
2. Update Status if warranted:
   - Evidence building → CONFIRMED
   - Counter-evidence mounting → CHALLENGED
   - Invalidation trigger hit → close it

### Closing a Thesis
When a thesis resolves (target hit, stop hit, time expired, invalidated):
1. Set Status to CLOSED-WIN / CLOSED-LOSS / EXPIRED
2. Set Closed date
3. Write a Resolution note (2-3 sentences: what happened, what was learned)
4. Remove related thesis linkage from any active positions if relevant

### Weekly Thesis Review
At each weekly rollup, run through all ACTIVE theses:
- Has any evidence accumulated this week? → append it
- Has any thesis been invalidated? → close it
- Has any thesis been clearly confirmed? → note it, decide if still worth holding
- Any new theses to open based on the week's research?

---

## Thesis Review Output Format

```
### 📌 Thesis Tracker — [DATE]

| ID | Title | Direction | Status | Days Open | Signal This Week |
|----|-------|-----------|--------|-----------|-----------------|
| T-001 | [title] | Long | ACTIVE | X | ✅ Confirming |
| T-002 | [title] | Short | CHALLENGED | X | ⚠️ Counter-evidence |

**Needs Attention:**
- T-002: [Describe the counter-evidence. Should this be closed?]

**New Thesis Candidates:**
- [Any new views emerging from recent research worth formalizing?]
```

---

## Quality Standards for Theses

A good thesis has:
- A **specific, falsifiable** statement (not "I think tech is interesting")
- A **clear invalidation condition** ("Close if SPY breaks 200-day MA on volume")
- A **time horizon** (not open-ended)
- **Evidence tracking** that distinguishes signal from noise

A bad thesis:
- "I'm bullish on stocks" — too vague
- No invalidation condition — can never be wrong
- No time horizon — can be held indefinitely without accountability

