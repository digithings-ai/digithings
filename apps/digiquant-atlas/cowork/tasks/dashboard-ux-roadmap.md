# Atlas Dashboard UX — Plan Review & Remaining Work

This file reconciles the original dashboard UX audit with **what is implemented** and lists **what is left**, in priority order.

---

## Completed (high level)

| Area | Delivered |
|------|-----------|
| **Overview** | Regime hero (pulse, as-of, badges), KPI strip + NAV sparkline, 3-column grid (positions / actionable+risk / macro pulse), thesis status dots + table, benchmark vs SPY inception blurb, latest-run quick links, redundant bottom nav removed, subtle regime inset glow, KPI stagger animation |
| **Overview** | 7-day position-changes subtitle on "Active positions" KPI |
| **Sidebar** | Last run, regime pill, ⌘K hint |
| **Portfolio** | Activity 2nd tab; Intelligence label; allocations table first + donut centers + target vs actual; performance summary + taller charts + advanced open + NAV reference lines for activity dates; command palette |
| **Portfolio — Allocations** | Category horizontal-bar comparison card above pie charts |
| **Portfolio — Intelligence** | "Browse history" label above MiniCalendar; thesis book (weights + tracker) moved above sleeve chart; PM doc display names use `canonicalResearchTitle`; thesis tracker rows have status-based left border accent |
| **Portfolio — Performance** | Daily P&L "Not enough data in range" copy when null; NAV chart tooltips enriched with position events (ticker + event type) on activity-marker dates |
| **Research** | Daily Digest tab; auto-open latest digest; delta banner prominence; digest TOC + jump nav; "Latest run" line; digest first-paragraph preview text shown in file list |
| **Global** | Command palette (⌘/Ctrl+K) with search, mouse + keyboard nav, thesis shortcuts; recent run dates added; fuzzy sort prioritises title-start matches |

---

## Remaining work

### P2 — Optional / deferred polish

- [ ] **Overview — actionable / risk "confidence"**  
  Plan suggested high/medium/low dots per bullet. Requires **structured data** (digest JSON) or agreed heuristics; skip until format exists.

- [ ] **Overview — numeric count-up on KPIs**  
  Optional `requestAnimationFrame` or CSS-only emphasis; keep perf and SSR/export constraints in mind.

- [ ] **Stronger regime atmosphere**  
  Optional full-page gradient tint (audit flagged as invasive). Current: inset wash only. Decide product-wise, then implement or explicitly reject.

### P3 — Larger / strategic (defer unless product commits)

- [ ] **Research — cross-digest synthesis**  
  "What changed across the last N digests?" — needs backend or client aggregation + UI surface; not a small patch.

- [ ] **Performance — regime change / rebalance markers**  
  Overlay regime transitions or rebalance events on the NAV series (beyond activity dates already shown).

- [ ] **Sleeve chart — click-through to PM docs for a date**  
  Wire chart selection to open the same PM doc flow as the calendar.

---

## Verification ✓

- [x] All routes verified: `/`, `/portfolio?tab=*`, `/research?tab=*`, `date`, `docKey`, `thesis`.  
- [x] Static export build (`next build`) passes with exit code 0.  
- [x] No TypeScript type errors.
- [x] No new lint errors introduced.
