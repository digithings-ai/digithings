# Deep scan: graphite.com

- **URL:** https://graphite.com
- **Audit:** 2026-06-29
- **Methods:** Homepage, /features, /pricing, /docs; Playwright mobile 390×844; design-bites CSS extraction

---

## 1. Site map (pages audited)

| URL | Type | Primary CTA |
|-----|------|-------------|
| `/` | Marketing homepage | "Get started for free" |
| `/features` | Product deep-dive (long scroll) | "Install the CLI" / "Get started" |
| `/features/ai-reviews` | Feature subpage | (linked from footer) |
| `/features/agents` | Feature subpage | — |
| `/features/chat` | Feature subpage | "Try Graphite Chat" |
| `/pricing` | Pricing + comparison table | "Start free trial" / "Sign up" |
| `/docs` | Docs hub (Mintlify) | External docs index |
| `/customers` | Social proof index | — |
| `/customer/{slug}` | Case studies (Semgrep, Shopify, Ramp, Asana, Tecton) | — |
| `/blog` | Content | — |
| `/guides` | Educational | — |
| `/stacking` | Workflow explainer | — |
| `/careers` | Hiring | — |
| `app.graphite.com` | Product app | "Log in" / "Sign up" |

**Footer IA (4 columns):** Features · Company · Resources · Connect

---

## 2. Global design tokens (inferred)

### Palette

| Token | Value | Role |
|-------|-------|------|
| `--bg-page` | `#0a0a0a` | zinc-950 canvas |
| `--surface-900` | `#18181b` | panels, nav on scroll |
| `--surface-800` | `#27272a` | cards, PR UI |
| `--surface-700` | `#3f3f46` | elevated |
| `--text-primary` | `#e8e8ed` | body, headings |
| `--text-secondary` | `#a1a1a6` | captions |
| `--text-nav` | white @ 60% → 100% hover | nav links |
| `--accent-brand` | `#ff8833` | primary CTA, rare highlights |
| `--border` | white @ 10% | universal hairline |
| `--error` | `#ffa6b2` | semantic |
| `--success` | `#a0e3a6` | semantic |

Footer accent blocks only: orange, yellow, cyan, blue (not in product chrome).

### Typography

| Role | Face | Size / weight |
|------|------|----------------|
| UI | Matter | 14–16px / 400–500 |
| h1 (hero) | Matter | ~36px / 500, lh 40px |
| h2 (section) | Matter | varies; often statement-scale |
| h3 (feature) | Matter | ~24px / 600 |
| Body | Matter | 16px / 400, lh 20–24px |
| Code | DM Mono / JetBrains | PR diffs, CLI |
| Ligatures | off | `liga: 0` for dev readability |

### Radius & shadow

- Buttons/cards: **8–10px** (not pill-shaped in core UI)
- Shadow: `0 1px 3px rgba(0,0,0,0.1)` — minimal; elevation via surface steps

### Motion

- **Glide easing:** custom `linear()` spring-like curve, **~0.6s** baseline
- Primary reveal: `translateY` + `opacity`
- Scroll-pinned feature carousel with **progress indicator**
- Clip-path reveals, footer marquee on accent blocks

### Layout

- Max content width ~**1216px** (`--header-right`)
- Product embed artboard: **800px**, scaled via `min(1, calc(100cqw - 2rem) / 800px)`
- Breakpoints tuned at: 554, 767, 768, 960, 1024, 1158, 1224, 1280, 1440px

---

## 3. Navigation system

### Desktop

- Logo left · Features / Resources (dropdowns) / Customers / Docs / Pricing / Contact
- Right cluster: **Log in** (ghost) · **Sign up** (primary orange)
- Announcement bar above nav (dismissible / clickable): product news
- Nav background: transparent → zinc glass on scroll
- Link hover: opacity 60% → 100%, **no color change**

### Mobile (Playwright 390×844, verified)

- Announcement bar: full width, 48px tall, tappable "Read more"
- Header: 62px — logo left; **Log in + Sign up** remain visible; **Menu** button right (28×28)
- Menu opens **`dialog "Navigation"`** full viewport below header (~795px tall)
  - Close button top-right (32×32)
  - List items 50px tall: Features (expandable), Resources (expandable), Customers, Docs, Pricing, Contact
  - Footer of sheet: social icon row (Contact, Slack, GitHub, X, LinkedIn, YouTube) + ©2026
- **No separate dimming scrim observed** — dialog covers content; page scroll locked implicitly

### Sticky / scroll

- Header stays fixed; announcement + nav stack
- No auto-hide on scroll down (observed on mobile homepage)

---

## 4. Component catalog

### Announcement bar

- Full-width strip above nav
- Copy: "Cursor Cloud Agents are now in Graphite. Create, review, and ship without leaving your PR."
- CTA: "Read more" + arrow icon
- `region "Announcement"` — clickable entire bar

### Primary button

- Orange fill `#ff8833`, white text, ~35px height, 10px radius
- Optional dual-arrow icon trailing on "Sign up" / "Start free trial"
- Labels: "Get started for free", "Start free trial", "Start stacking", "Start chatting"

### Secondary button

- Ghost/outline on dark; "Request a demo", "Log in"
- Often pairs with primary in hero (stacked on mobile)

### Friction reducer (hero)

> "Free for your first 30 days. No credit card required. Synced with your GitHub account."

Three trust bullets in one muted paragraph under CTAs.

### Logo trust strip

- Horizontal list of customer logos (Robinhood, Shopify, Figma, DataDog on mobile)
- Grayscale, ~60×24 per logo
- Placed **below** hero CTAs, above product video

### Hero video / feature picker

- Large video thumbnail with Play overlay
- Horizontal icon strip below: Stacked PRs · PR page · AI code review · Chat · Merge queue · PR inbox · Dev metrics
- Each icon ~53×53 tap target — switches video/feature context

### Case study carousel

- Horizontal scroll/cards: `{Company} × Graphite` label + outcome headline
- Examples: "How stacked PRs help Semgrep engineers move faster"
- Prev/Next slide buttons at bottom
- Card ~333×231 with partner artwork

### Scroll-pinned feature stack (homepage)

Five blocks on mobile (stacked vertically; desktop uses pin + swap):

1. "The AI reviewer you can collaborate with" + Graphite Chat UI
2. "Review faster, ship sooner" + AI code reviews UI
3. "Merge without conflicts or delays" + Merge queue UI
4. "Stay unblocked with stacked PRs" + Stacking UI
5. "Fast, focused reviews in a modern PR page" + PR page UI

Each: **h3** + paragraph + labeled product screenshot with overlay tag ("Graphite Chat", "AI code reviews", etc.)

### Feature section grid ("Everything you need to ship faster")

- h2: "Everything you need to ship faster"
- Sub: "One end-to-end tool to simplify and accelerate your workflow"
- Repeated pattern per feature:
  - h3 + paragraph
  - Primary or text link ("Learn more →", "Read the docs →", "Read about CI Optimizations →")
  - Product screenshot (CLI, inbox, Slack, CI optimizer, platform icons, chat)
- Closing link: "Read more about all our features →" → `/features`

### PR code review inline (features page)

- Live diff snippet with line numbers
- AI reviewer comment bubble ("Diamond") with thumbs up/down
- Demonstrates in-context review UX

### Pricing cards

- Tier names: **Hobby · Starter · Team · Enterprise**
- "Most popular" badge on Team
- Annual billing toggle: "Annual billing (20% off)"
- CTA per card: "Sign up" / "Get started" / "Start free trial" / contact sales
- Enterprise: bullet list only, no price

### Comparison table

- Rows: Pull requests, GitHub sync, Inbox, Integrations, Stacking, Chat, AI reviews, Merge queue, Admin…
- Columns per tier with checkmarks / "Limited" / "Basic" / "Advanced"

### FAQ accordion

- "Frequently asked questions" — expandable questions
- Closing: "Still have questions? Reach out to our team."

### Footer

- 4-column link grid (collapses to 2×2 on mobile)
- Status link: "All systems operational" (green indicator)
- Large neon sign brand image at bottom (personality moment)
- © Graphite 2026

---

## 5. Page-by-page breakdown

### Homepage `/`

| # | Section | Headline / key copy |
|---|---------|---------------------|
| 1 | Announcement | Cursor Cloud Agents integration |
| 2 | Hero | "The next generation of code review." |
| 3 | Trust | Logo strip |
| 4 | Product | Video + feature icon picker |
| 5 | Case studies | Carousel (5 customers) |
| 6 | Features (pinned/stack) | 5 capability blocks with UI |
| 7 | Platform grid | CLI, inbox, Slack, CI, merge queue, chat |
| 8 | Infrastructure | 3 pillars: change / GitHub / Git |
| 9 | Closing CTA | "Built for the world's fastest engineering teams…" |
| 10 | Footer | Links + neon sign |

### Features `/features`

- Hero: "The new standard for developer infrastructure"
- Sub-features with CLI command examples (`gt create`, `gt log`, `gt submit`)
- Long-form sections: CLI, Inbox, Chat (with diff demo), Insights, Merge Queue
- Each section: h3 + bullets + "See more" / "Learn more" / "Install the CLI"

### Pricing `/pricing`

- "One tool. Everything you need to review and ship faster."
- 4 tiers + comparison matrix + FAQ + closing CTA

---

## 6. Scroll & interaction behaviors

| Behavior | Where | Notes |
|----------|-------|-------|
| Scroll-pinned feature swap | Homepage (desktop) | Progress bar; subsection headline + visual + CTA per slide |
| Horizontal case study carousel | Homepage | Arrow buttons; swipe on touch |
| Video play | Hero | Click thumbnail → play features video |
| Feature icon picker | Below video | Switches featured capability |
| Nav glass on scroll | Global | Background darkens |
| Hover on nav | Desktop | Opacity fade only |
| AI review demo | Features/chat | Inline diff + feedback UI |

**Reduced motion:** Not verified in audit; assume `@media (prefers-reduced-motion)` on marketing animations.

---

## 7. Copy & IA patterns

### Headline formula

- **Category redefinition:** "The next generation of code review."
- **Outcome h3:** "Review faster, ship sooner" / "Merge without conflicts or delays"
- **Platform h2:** "Everything you need to ship faster"

### CTA library

| CTA | Context |
|-----|---------|
| Get started for free | Hero primary |
| Request a demo | Hero secondary, closing |
| Start free trial | Pricing, closing |
| Sign up | Nav, pricing tiers |
| Learn more → | Feature cells (arrow suffix) |
| Read the docs → | Integration features |
| Start stacking | CLI feature |
| Start chatting | Chat feature |
| Install the CLI | Features page |

### Link arrow pattern

Text links end with `→` or trailing arrow icon — "Learn about agentic development →"

### Case study label

`{Partner} × Graphite` — monospace-feel label above quote

---

## 8. Mobile-specific patterns

- Hero h1 wraps to 3 lines at 390px width
- CTAs stack vertically (full width ~342px)
- Primary + secondary buttons each ~35px tall, full row width when stacked
- Feature video scales to ~321×181
- Feature icon strip scrolls horizontally (7 items, some clipped)
- Case study cards horizontal scroll
- Feature blocks: copy above image (not side-by-side)
- Platform feature cards: single column ~340px wide
- Footer: 2-column link grid
- **Sign up stays in header** on mobile (unlike nav links)

---

## 9. Adopt / Adapt / Avoid (DigiThings)

| Adopt | Adapt | Avoid |
|-------|-------|-------|
| Scroll-pinned **one** flagship section | Olympus pipeline, not PR UI | Orange/zinc palette literally |
| Product UI frames with labels | DigiChat, tearsheets, Olympus | 5 separate 400vh scroll sections |
| Glide motion token | `--ease-glide` in tokens.css | Nine breakpoints day one |
| Friction reducer under CTA | "open core · self-hosted · BYOK" | Fake "limited AI" tiers |
| Case study `{X} × digiquant` format | Real adopters when available | Announcement bar without real news |
| Comparison table for pricing | digiquant OSS vs cloud | Hiding GitHub on mobile |
| Logo strip below hero CTAs | Nautilus, GitHub stars | — |
| Learn more → link pattern | Per-module docs links | — |

---

## 10. Open questions / re-audit

- [ ] Desktop scroll-pinned progress rail (verify with full browser, not fetch)
- [ ] Light mode (Graphite appears dark-only on marketing)
- [ ] Exact Matter font loading / fallback stack
- [ ] Hover states on primary button (shadow lift?)
