# Copy & information architecture patterns

Extracted from live site copy on Graphite, Cursor, and x.ai — 2026-06-29.

---

## 1. Hero headline formulas

| Site | Headline | Structure |
|------|----------|-----------|
| Graphite | "The next generation of code review." | [Superlative era] + [category] |
| Cursor | "Cursor is your coding agent for building ambitious software." | [Product] is [role] for [ambition] |
| x.ai | "Frontier AI models for everything you build." | [Quality] + [category] for [builder outcome] |

**DigiThings equivalents (draft):**

- digithings: "Build agents on infrastructure you own." (ownership — already live)
- digiquant: "A quant hedge fund. *In a box you own.*" (category + twist)
- digichat: product-as-hero — let UI speak

---

## 2. Subhead patterns

| Site | Example | Length |
|------|---------|--------|
| Graphite | "Graphite is the AI code review platform where teams ship higher quality code, faster." | ~20 words, dual outcome |
| Cursor | (minimal on mobile — demo carries weight) | — |
| x.ai | "Reasoning, code, voice, images, and video. Trained on the world's largest supercluster." | modality list + proof |

**Pattern:** Either **short sub** + big visual, or **modality/enumeration** + credibility anchor.

---

## 3. CTA verb library

### Graphite

- Get started for free
- Request a demo
- Start free trial
- Sign up / Log in
- Learn more →
- Read the docs →
- Start stacking / Start chatting
- Install the CLI
- See more

### Cursor

- Download for macOS
- Get started →
- Request a demo
- Contact sales / Talk to the team
- Copy command
- Learn about {feature} →
- Explore models ↗
- Join us →
- Get Pro / Get Teams

### x.ai

- Get API Key
- Read Docs
- Start building
- Explore →
- Contact Sales
- All posts / Read More

### DigiThings mapping

| Their pattern | Our literal CTA |
|---------------|-----------------|
| Download for macOS | `git clone` / docker compose |
| Get API Key | `make stack-local` / issue-key |
| Get started | `ask digichat` / `open olympus` |
| Start free trial | `run a backtest` (digiquant) |
| Explore → | `read docs` / module pages |
| Contact sales | `contact@digithings.ai` |

**Avoid:** "Get started" without naming the destination.

---

## 4. Friction reducers (under primary CTA)

| Site | Text |
|------|------|
| Graphite | "Free for your first 30 days. No credit card required. Synced with your GitHub account." |
| Cursor (Hobby) | "No credit card required" + "Limited Agent requests" |
| x.ai | "Usage-based pricing" / "Automatically increasing rate limits" |

**DigiThings draft:**

> open core · self-hosted · BYOK · audit-on by default

Or digiquant-specific:

> MIT license · NautilusTrader · tearsheets from real backtests

---

## 5. Section title patterns

| Pattern | Example | Site |
|---------|---------|------|
| Outcome h2 | "Everything you need to ship faster" | Graphite |
| Movement h2 | "The new way to build software." | Cursor |
| Frontier h2 | "Stay on the frontier" | Cursor |
| Infrastructure h2 | "Developer infrastructure built for your team" | Graphite |
| Scale h2 | "AI is changing how software is built." | Cursor enterprise |
| Mono eyebrow + h2 | "For developers" / "One API. Every modality." | x.ai |
| Question FAQ | "Frequently asked questions" | Graphite/Cursor pricing |

**Our kickers:** `// the architecture` — already aligned with xAI mono eyebrow intent.

---

## 6. Feature cell structure

Universal pattern across all three:

```
[eyebrow optional]
h3: {outcome in 4–8 words}
p:  {one sentence mechanism}
a:  {Learn more → | Explore →}
[product visual]
```

Examples:

- Graphite: "Review faster, ship sooner" + AI reviews screenshot
- Cursor: "Agents turn ideas into code" + agent UI
- x.ai: "Text generation" + capability description

---

## 7. Social proof formats

| Format | Template | Example |
|--------|----------|---------|
| Case study label | `{Co} × {Product}` | Semgrep × Graphite |
| Quote | "{Impact statement}" — Name, Title, Company | Patrick Collison, Stripe |
| Stat | `{NN}%` + label | 64% Fortune 500 (Cursor) |
| Scale stat | `{NNM}+` + unit | 300M+ queries daily (x.ai) |
| Logo strip | (no copy) | Trusted by… |

---

## 8. Pricing voice

| Site | Tier names | Bullets |
|------|------------|---------|
| Graphite | Hobby, Starter, Team, Enterprise | Feature matrix + "Limited" / "Unlimited" |
| Cursor | Hobby, Individual, Teams, Enterprise | ✓ checkmarks, nested Pro/Pro+/Ultra |
| x.ai | Self-serve vs Sales | Per-million-token $, modality tables |

**Open-core angle for us:** Hobby = self-hosted stack; Enterprise = support/SLA — not fake "limited AI."

---

## 9. Footer IA

| Site | Columns |
|------|---------|
| Graphite | Features · Company · Resources · Connect |
| Cursor | Product · Resources · Company · Legal · Connect |
| x.ai | Minimal + news links |

**DigiThings:** Architecture · Docs · Contact · digiquant.io · GitHub · digichat

---

## 10. Announcement bar copy

| Site | Example |
|------|---------|
| Graphite | "Cursor Cloud Agents are now in Graphite. Create, review, and ship without leaving your PR." |
| x.ai | "New — Grok Build Beta" (inferred) |

**Rule:** Only ship announcement bar when there is real news — Graphite models integration story.

---

## 11. DigiThings copy guide (draft)

### Voice

- **Technical, precise, ownership-oriented** — closer to x.ai infrastructure than Cursor consumer warmth
- Lowercase product names: digithings, digiquant, digichat
- Proper nouns: Olympus, Atlas, Hermes, NautilusTrader

### Page-level IA template (marketing)

1. Hero: headline + sub + literal CTA + friction line + product frame
2. Trust: logos or stats (real only)
3. Features: bento OR one scrolly (not both competing)
4. Social proof: quotes or case studies
5. Developer band: code sample or CLI (x.ai/Cursor)
6. Changelog/news
7. Final CTA
8. Footer

### Per-surface emphasis

| Surface | Lead reference for copy |
|---------|-------------------------|
| digithings.ai | Cursor IA + x.ai API band |
| digiquant.io | Graphite outcomes + Cursor bento |
| digichat | Cursor product-as-hero |
| Olympus / twelve-x | x.ai mono labels, no marketing fluff |
