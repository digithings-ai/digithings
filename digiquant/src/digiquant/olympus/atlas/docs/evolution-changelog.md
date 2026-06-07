# Pipeline Evolution Changelog

> This document tracks every approved improvement to the digiquant-atlas pipeline.
> Each entry records what changed, why, and the measurable impact expected.
> This file is maintained by the daily digest's Phase 9 self-improvement loop.

---

## How This Works

The daily digest pipeline includes a **post-mortem phase** (Phase 9) that evaluates each run's quality, rates data sources, and identifies potential improvements. When the agent identifies a refinement, it files a **proposal** in `data/agent-cache/daily/YYYY-MM-DD/evolution/proposals.md`. Approved proposals are applied and documented here as a permanent changelog.

**Guardrails**: The agent cannot modify the output schema, risk profile, or memory format. All changes require explicit user approval before being applied.

---

## Applied Improvements

*(No improvements applied yet — pipeline is in its inaugural state)*

---

## Changelog Format

Each applied improvement follows this structure:

```
### [IMP-XXX] Title
- **Date Applied**: YYYY-MM-DD
- **Proposal ID**: P-XXX
- **Category**: Source Addition | Skill Refinement | Template Update | Efficiency
- **Target File(s)**: path/to/file
- **Change Description**: What was modified
- **Rationale**: Why this improvement was needed (with data from quality-log or sources.md)
- **Expected Impact**: What measurable improvement is anticipated
- **Commit**: [commit hash]
```

---

## Improvement Statistics

| Metric | Value |
|--------|-------|
| Total Proposals Filed | 0 |
| Approved & Applied | 0 |
| Rejected | 0 |
| Pending Review | 0 |
| Pipeline Version | 1.0 (Inaugural) |
| Last Updated | 2026-04-05 |
