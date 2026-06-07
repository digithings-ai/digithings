---
name: digiquant-atlas
description: >
  Run this skill to produce the full daily market digest. Triggers when the user says "run today's digest",
  "daily analysis", "market update", "morning brief", or pastes the new-day prompt. UPGRADED: This skill
  now delegates to the orchestrator skill which runs a full 7-phase pipeline with dedicated sub-agents for
  each sector, asset class, and alternative data source. Always use this skill for any full market analysis session.
---

# digiquant-atlas — Pointer to Orchestrator (v2)

> **This skill has been superseded by the full orchestrator pipeline.**
> Follow the instructions below to run the upgraded system.

---

## Action Required

When this skill is triggered by any of these phrases:
- "run today's digest"
- "daily analysis"
- "market update"
- "morning brief"
- Pasting the `scripts/cowork-daily-prompt.txt` content

**Immediately load and follow: `skills/orchestrator/SKILL.md`**

The orchestrator runs the complete pipeline:
1. **Phase 1**: Alternative Data (sentiment, CTA positioning, options, politician signals)
2. **Phase 2**: Institutional Intelligence (ETF flows, hedge fund intel)
3. **Phase 3**: Macro Analysis
4. **Phase 4**: Asset Classes (bonds, commodities, forex, crypto, international)
5. **Phase 5**: US Equities + 11 GICS Sector Sub-Agents
6. **Phase 7**: Master digest synthesis (JSON-first, DB-first publish)

Output is stored DB-first (Supabase). Markdown is a derived view.

---

## Quality Standards (Preserved)

- Be direct. State the bias. Don't hedge everything into meaningless mush.
- Use the user's preferences to filter for what matters to THEM, not general market commentary.
- When evidence is conflicted, say so clearly and explain both sides.
- Flag anything that contradicts the user's active theses.
- Do not repeat the same sentence twice in different sections.
- Every section should end with an implication or action, not just a description.

