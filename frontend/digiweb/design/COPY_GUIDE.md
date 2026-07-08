# DigiThings copy & information architecture guide

**Status:** Living document · **Last updated:** 2026-06-30

Authoritative voice, CTA, and section-map reference for all public surfaces. Implements Layer D of the [design evolution spec](../../docs/superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md) and extends [`references/scans/copy-patterns.md`](references/scans/copy-patterns.md).

**Related:** [`EVOLUTION.md`](EVOLUTION.md) (strategy) · [`README.md`](README.md) (tokens) · [Epic #1200](https://github.com/digithings-ai/digithings/issues/1200)

---

## 1. Voice & tone

| Principle | Rule |
|-----------|------|
| Tone | Technical, precise, ownership-oriented — closer to x.ai infrastructure than Cursor consumer warmth |
| Product names | lowercase: digithings, digiquant, digichat |
| Proper nouns | Olympus, Atlas, Hermes, NautilusTrader, LangGraph, LiteLLM, Polars |
| CTAs | **Literal destinations** — never naked "Get started" |
| Proof | Real data only — GitHub stars, backtest counts, release dates |
| Serif | Marketing hero display only; dashboards use sans + mono |

---

## 2. Headline formulas

| Surface | Formula | Example |
|---------|---------|---------|
| digithings | [ownership outcome] | "Build agents on infrastructure you own." |
| digiquant | [category] + [twist] | "A quant hedge fund. *In a box you own.*" |
| digichat | (product speaks) | — no marketing h1 above terminal |
| Olympus / twelve-x | [page function] | "Atlas pipeline" / "Today's snapshot" |

Reference patterns (Graphite, Cursor, x.ai): see [`copy-patterns.md` §1–2](references/scans/copy-patterns.md).

---

## 3. Subhead patterns

Use one of two shapes:

1. **Short sub + big visual** — ~15–20 words, dual outcome (Graphite style).
2. **Modality list + credibility anchor** — enumerate capabilities, anchor on real stack (x.ai style).

**Draft subs:**

- **digithings:** "LangGraph orchestration, MCP tools, and open-core modules — self-hosted or cloud."
- **digiquant:** "Backtest · optimize · paper · live — NautilusTrader under the hood."

---

## 4. Section title patterns

| Pattern | Example | Use when |
|---------|---------|----------|
| Outcome h2 | "Everything you need to ship faster" | Feature bands |
| Movement h2 | "The new way to build software." | Brand story |
| Mono eyebrow + h2 | `// the architecture` + h2 | x.ai-style infrastructure sections |
| Question FAQ | "Frequently asked questions" | Pricing / self-host FAQ |

**Kickers:** Keep `// section` mono eyebrows on marketing; dashboards use mono uppercase labels only for metrics.

---

## 5. Feature cell structure

Universal bento / capability cell:

```
[optional eyebrow]
h3: {outcome in 4–8 words}
p:  {one sentence mechanism}
a:  {Learn more → | Explore →}
[product visual in ProductFrame]
```

Examples from references: Graphite "Review faster, ship sooner"; Cursor "Agents turn ideas into code"; x.ai modality + capability description.

---

## 6. Literal CTA library

### Per-surface matrix

| Pattern | digithings.ai | digiquant.io | DigiChat | Olympus |
|---------|---------------|--------------|----------|---------|
| Primary | `ask digichat` | `open olympus` | `sign in` / `new chat` | context action |
| Secondary | `read docs` → | `browse strategies` → | `view on github` → | `export` / `run` |
| Developer | `make stack-local` | `git clone …` | `copy api command` | — |
| Explore | `explore digigraph` → | `view tearsheets` → | — | tab label |
| Contact | `contact us` | `contact@digithings.ai` | — | — |

### Mapping from reference sites

| Their pattern | Our literal CTA |
|---------------|-----------------|
| Download for macOS | `git clone` / `docker compose` |
| Get API Key | `make stack-local` / issue-key |
| Get started | `ask digichat` / `open olympus` |
| Start free trial | `run a backtest` (digiquant) |
| Explore → | `read docs` / module pages |
| Contact sales | `contact@digithings.ai` |

**Avoid:** "Get started" without naming the destination.

---

## 7. Friction reducers

Place directly under the primary CTA (muted, `--text-secondary`).

| Surface | Draft line |
|---------|------------|
| digithings.ai | `open core · self-hosted · MCP-first · BYOK` |
| digiquant.io | `MIT license · NautilusTrader · tearsheets from real backtests` |
| DigiChat | `bring your own key · audit log on by default` |

---

## 8. Footer IA

### Marketing landings

Four columns: **Architecture · Docs · Contact · Connect**

Include cross-links: digiquant.io · GitHub · digichat where relevant.

### Dashboard (Olympus / twelve-x)

Minimal — no marketing columns. Literal nav labels only; document in Olympus subpage chrome (#1220).

---

## 9. Marketing vs dashboard IA templates

### Marketing template (digithings, digiquant)

1. Hero — headline + sub + literal CTA + friction + `ProductFrame`
2. Trust — logo/integration strip or GitHub stars (real only)
3. Features — bento OR one scrolly (not both competing)
4. Social proof — quotes or case studies (real attribution only)
5. Developer band — `CodeSampleBand` or stack-local command
6. Changelog / news — `ChangelogBand`
7. Closing CTA — `ClosingCtaBand`
8. Footer

### Dashboard template (Olympus, twelve-x)

1. Sticky tab bar — literal labels
2. Page title — Instrument Serif display, one line
3. KPI row — mono uppercase labels, tabular nums
4. Content panels — flat surface, hairline
5. No marketing sections, no mesh, no announcement bar

### DigiChat (product-as-hero)

1. Nav — minimal: brand · sign in · theme
2. Chat chrome = hero — no marketing h1 above terminal
3. Sample prompts in empty state
4. `CodeSampleBand` below fold for API/BYOK
5. Footer — minimal

---

## 10. Per-surface section maps

### digithings.ai (Cursor IA + x.ai API band)

1. Hero — headline + sub + literal CTA + friction + `ProductFrame` (supervisor/chat)
2. Trust — logo/integration strip or GitHub stars
3. Modules — **bento grid** (not long scroll) — #1211
4. Architecture — optional **one** scrolly OR manifest interactivity (not both)
5. Developer — `CodeSampleBand` or stack-local command
6. Changelog — `ChangelogBand` + horizontal scroll on mobile — #1212
7. Closing CTA — `ClosingCtaBand`
8. Footer — 4 columns

**Draft hero copy:**

- **h1:** "Build agents on infrastructure you own."
- **sub:** "LangGraph orchestration, MCP tools, and open-core modules — self-hosted or cloud."
- **primary:** `ask digichat` · **secondary:** `read docs` →

### digiquant.io (Graphite outcomes + Cursor bento)

1. Hero — Fraunces h1 + modality sub + CTAs + stats — #1213
2. Optional hero picker — Olympus / strategies / pipeline — Phase E
3. **Olympus scrolly** (only pin) + progress rail — #1215
4. Bento — Pipeline · Strategies · Pricing — #1214
5. Strategy suite — existing scroll stack (second story, not second pin)
6. Pricing — `PricingMatrix` + `FaqAccordion` — Phase E
7. Closing CTA — `open olympus`
8. Footer

**Draft hero copy:**

- **h1:** "A quant hedge fund. *In a box you own.*"
- **sub:** "Backtest · optimize · paper · live — NautilusTrader under the hood."
- **primary:** `open olympus` · **secondary:** `browse strategies` →

### DigiChat (#1218)

See §9 product-as-hero template. Marketing route = full chat chrome; embed route stays minimal (no marketing chrome in iframe).

### Olympus / twelve-x (#1216, #1217, #1220)

See §9 dashboard template. **Explicit reject list:** mesh, Fraunces/serif, scroll pinning, hero sections, announcement bar.

---

## 11. Announcement bar copy template

Only ship when there is real news (Graphite integration-bar model).

**Structure:** `{Product/integration} is now {action}. {One-sentence benefit}.` + link target.

**Example (placeholder — enable via `announcement.json` when true):**

> LangGraph 0.3 supervisor patterns are live in digigraph. Run multi-agent workflows without leaving your stack.

**Rule:** Build `AnnouncementBar` primitive disabled by default; enable via content file when merging integrations or releases.

---

## 12. Anti-patterns

1. Generic AI hero — headline + two buttons + chart sidebar
2. Fake ticker / fake enterprise stats
3. Decorative eyebrow pills with no action
4. Five scroll-pinned sections on one page
5. Mesh on product screenshots inside frames
6. Multiple primary CTAs in nav bar
7. Glass on new dashboard components
8. Stock testimonials without real attribution
9. "Get started" without naming the destination
10. Fake tier limits ("limited AI requests") on open-core pricing

Full list: [`EVOLUTION.md` §10](EVOLUTION.md) · [design spec §6](../../docs/superpowers/specs/2026-06-30-frontend-design-evolution-layers-design.md).

---

## 13. Maintenance

- Update this guide when a surface ships new section types or when reference sites redesign
- Landing copy implementation is tracked in Phase C issues (#1210–#1215); primitives in Phase B/E
- Re-audit [`copy-patterns.md`](references/scans/copy-patterns.md) when Graphite, Cursor, or x.ai ship major homepage changes
