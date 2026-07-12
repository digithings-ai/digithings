# Deep scan: cursor.com

- **URL:** https://cursor.com
- **Audit:** 2026-06-29
- **Methods:** Homepage, /features, /pricing, /enterprise, /changelog; Playwright mobile 390×844; BestSaaSWebDesigns palette extraction

---

## 1. Site map (pages audited)

| URL | Type | Primary CTA |
|-----|------|-------------|
| `/` | Marketing homepage | "Get started" / "Download for macOS" |
| `/home` | Logo target (same as /) | — |
| `/features` | Redirect/alias to homepage sections | — |
| `/product` | Agent product page | "Learn about agentic development →" |
| `/tab` | Tab autocomplete feature | — |
| `/docs/cloud-agent` | Docs | — |
| `/pricing` | Pricing tiers | "Get Pro" / "Get Teams" / "Download" |
| `/enterprise` | Enterprise sales | "Contact sales" / "Talk to the team" |
| `/changelog` | Release notes | — |
| `/changelog/*` | Individual releases | — |
| `/blog` | Content | — |
| `/blog/*` | Posts (Research / Product tags) | — |
| `/careers` | Hiring | "Join us" |
| `/security` | Trust / SOC2 | — |
| `/login` | Auth | "Get started" links here |
| `/dashboard` | "Sign in" target | — |

**Observed palette (light):** `#f7f8f3` bg · `#e3e2dd` borders · `#989ba4` muted · `#d3c9b9` warm accent touch  
**Stack:** Next.js + Tailwind CSS · Cursor Gothic display + Lato body (per third-party audits)

---

## 2. Global design tokens (inferred)

### Palette (light-first marketing)

| Token | Value | Role |
|-------|-------|------|
| `--bg-page` | `#f7f8f3` | warm off-white canvas |
| `--surface` | `#ffffff` | cards, product frames |
| `--border` | `#e3e2dd` | hairlines |
| `--text-primary` | near-black | headlines |
| `--text-muted` | `#989ba4` | secondary |
| `--accent-warm` | `#d3c9b9` | subtle decorative |

Dark mode: footer theme toggle (System / Light / Dark) — site supports theme switching.

### Typography

| Role | Treatment |
|------|-----------|
| Display | Cursor Gothic — tight tracking, large hero |
| Body | Lato / geometric sans — 16–18px |
| Hero h1 | ~2 lines at mobile; "Cursor is your coding agent for building ambitious software." |
| Section h2 | "The new way to build software." / "Stay on the frontier" |
| Feature h3 | Inside bento cards |
| Links | `→` suffix on CTAs ("Get started →", "Join us →") |

### Radius & shadow

- Product frames: `rounded-xl`, `shadow-2xl`, border
- Buttons: rounded, ~44px height on mobile primary
- Bento cards: large radius, soft shadow on hover (inferred)

### Motion

- **Minimal page-level scroll choreography** — standard document scroll
- Internal product demo animations (agent progress, tab completion)
- Logo strip static
- Testimonial horizontal scroll / carousel
- Changelog horizontal scroll on mobile (articles overflow viewport)

### Layout

- Hero: copy + CTA stack, then full-width product demo below (mobile)
- Bento: large linked cards (~353×856px each on mobile — tall cells)
- Section padding generous (`py-24` class equivalent)
- Max width ~1100–1200px (inferred)

---

## 3. Navigation system

### Desktop (inferred from structure)

- Logo → `/home`
- Links: Product areas, Pricing, Enterprise, Docs, Blog
- **Download for macOS** — platform-detected primary
- Sign in → `/dashboard`

### Mobile (Playwright 390×844, verified)

- Header: **56px** tall
- Logo left (~95×24)
- **Sign in** link visible (right of center)
- **Open navigation** button: 32×32 icon button (far right)
- Hidden nav panel exists in DOM (`navigation` at 0,0,390,844) — toggled by hamburger
- Skip link: "Skip to content" → `#main`

### Mobile menu (on open — structure from DOM)

- Full-height overlay navigation
- List of primary destinations
- (Full item list not expanded in snapshot — re-audit with menu open)

### Footer (mobile)

- 4 sections × 2 columns: Product · Resources · Company · Legal · Connect
- Theme toggle row: **System / Light / Dark** (3 segmented buttons)
- Language: "🌐 English ↓"
- © 2026 Anysphere, Inc. + SOC 2 Certified link

---

## 4. Component catalog

### Hero

- h1: "Cursor is your coding agent for building ambitious software."
- Primary: "Get started" → `/login` with trailing `→`
- Desktop also shows: "Download for macOS", "Request a demo"
- Product demo: multi-interface preview (Desktop + CLI) over brand background
- Accessibility: hidden description for screen readers explaining demo content

### Bento feature card (linked)

Large tappable card (~353×856 mobile):

```
h3: Agents turn ideas into code
body: Accelerate development by handing off tasks to Cursor, while you focus on making decisions.
link: Learn about agentic development →
[product UI: agent task UI]
```

Similar cards for:
- Cloud agents (task list UI, "Worked for 14m 22s")
- Terminal (`curl https://cursor.com/install -fsS | bash` + copy button)
- Tab autocomplete

### Agent task list UI (in bento)

- URL bar mock: `cursor.com/agent`
- Sections: "This Week" / "This Month" with task chips
- Conversation thread with status pills: "Explored 12 files", "Worked for 14m 22s"
- Model badge: "Agent · Opus 4.8"
- Input: "Add a follow up..."

### Copy command button

- Monospace block with install curl
- "Copy command" button — 44px tall full width on mobile

### Logo trust strip

- h2: "Trusted every day by teams that build world-class software"
- 2-row logo grid on mobile (8 logos)
- Grayscale marks

### Testimonial block

- h2: "The new way to build software."
- `figure` + `blockquote` per quote
- Attribution: Name + Title + Company (e.g. "Diana Hu, General Partner, Y Combinator")
- Horizontal scroll of multiple quotes on mobile

### Frontier section (3-up → stack)

- h2: "Stay on the frontier"
- Cards:
  1. Model picker UI — "Use the best model for every task" + dropdown mock
  2. Codebase Q&A — "Where are these menu label colors defined?"
  3. Enterprise — "Develop enduring software" → `/enterprise`

### Changelog band

- h2: "Changelog"
- Articles: date + version badge + title (horizontal scroll)
  - "Jun 29, 2026 — Cursor Mobile App for iOS"
  - "3.9 Jun 22, 2026 — Customize Cursor"
- Link: "See what's new in Cursor →"

### Blog highlights

- h2: "Recent highlights"
- Tag + category: Research / Product
- Title + author + read time
- "View all blog posts →"

### Closing CTA

- h2: "Try Cursor now."
- "Get started" button (centered on mobile)

### Pricing card

- Toggle: Monthly / Yearly
- Tiers: Hobby (Free) · Individual ($20/mo) · Teams ($40/user) · Enterprise (Custom)
- Sub-toggle on Individual: Pro / Pro+ / Ultra
- Bullets with ✓ prefix
- Friction: "No credit card required" on Hobby
- CTAs: "Download" / "Get Pro" / "Get Teams" / "Contact Sales"

### Enterprise stat strip

- "64% Fortune 500 companies using Cursor"
- "50,000+ Enterprises choose to build with Cursor"
- "100M+ Lines of enterprise code written per day"

### FAQ (pricing)

- "Questions & Answers" — accordion
- Practical questions: payment, usage limits, data privacy, resellers

---

## 5. Page-by-page breakdown

### Homepage `/`

| # | Section |
|---|---------|
| 1 | Hero + product demo |
| 2 | Logo strip |
| 3 | Bento: Agents |
| 4 | Bento: Cloud agents |
| 5 | Bento: Terminal install |
| 6 | Bento: Tab |
| 7 | Testimonials |
| 8 | Frontier (models, codebase, enterprise) |
| 9 | Changelog |
| 10 | Careers pitch + Join us |
| 11 | Blog highlights |
| 12 | Try Cursor now |
| 13 | Footer |

### Enterprise `/enterprise`

- Hero: "Develop enduring software at scale"
- CTA: "Talk to the team"
- Enterprise logo strip
- 3 proof blocks with executive quotes (Salesforce, Fox, PayPal)
- Stat strip (64%, 50k+, 100M+ lines)
- Feature grid: control, models, Bugbot PR UI mock
- Security/certification grid (12 items)
- Long testimonial wall
- Customer story cards with dates
- FAQ + "Contact sales"

### Changelog `/changelog`

- Dated entries with version numbers (3.9, 3.8, 3.7…)
- Long-form feature descriptions with `##` subheads
- "### Improvements (N)" bullet lists
- Product screenshots inline (inferred)

---

## 6. Scroll & interaction behaviors

| Behavior | Notes |
|----------|-------|
| Standard scroll | No pinned homepage sections |
| Horizontal overflow | Changelog cards, blog cards, testimonials |
| Bento hover | Card lift/shadow (desktop) |
| Copy command | Clipboard on terminal CTA |
| Theme toggle | Footer segmented control |
| Product demo | Interactive or video (agents bento) |

---

## 7. Copy & IA patterns

### Headline

- **Identity + ambition:** "Cursor is your coding agent for building ambitious software."
- **Social proof section:** "The new way to build software." (not a feature — a movement)
- **Frontier:** "Stay on the frontier"

### CTA verbs

| Phrase | Use |
|--------|-----|
| Download for macOS | Platform hero (desktop) |
| Get started | Primary conversion → login |
| Request a demo | Enterprise/eval |
| Contact sales | Enterprise |
| Copy command | Developer install |
| Learn about … → | Feature deep links |
| Explore models ↗ | External-style link |
| Join us → | Careers |

### Feature description

- **h3** outcome title (6–8 words)
- One sentence mechanism
- Optional `Learn about X →` link
- Product UI carries detail — not bullet lists in marketing

---

## 8. Mobile-specific patterns

- Hero CTA single prominent "Get started" (Download de-emphasized or below fold on narrow)
- Product demo scales down but remains center stage
- Bento cards full viewport width, **very tall** (~856px) — each feature is a chapter
- Testimonials scroll horizontally
- Changelog 4 articles in horizontal strip (262px each)
- Footer theme + language controls remain accessible
- Sign in always visible in header (not buried in menu)

---

## 9. Adopt / Adapt / Avoid (DigiThings)

| Adopt | Adapt | Avoid |
|-------|-------|-------|
| Hero: headline + one CTA + demo | DigiChat/Olympus embed | Warm off-white if it fights our dark mesh identity |
| Bento linked cards | Module grid on digithings | 856px-tall mobile cards (too long) |
| Literal CTAs | `make stack-local`, `ask digichat` | "Get started" without destination |
| Changelog band | GitHub releases | Duplicate homepage content in /features |
| Testimonial carousel | Builder quotes | Stock enterprise stats without data |
| Copy command row | docker compose / make | — |
| Pricing FAQ accordion | digiquant pricing | — |
| Footer theme toggle | Already have ThemeToggle | — |
| SOC2 / trust footer link | Open-core security docs | — |

---

## 10. Open questions

- [ ] Full mobile nav item list (expand hamburger in Playwright)
- [ ] Desktop two-column hero layout measurements
- [ ] Dark mode marketing page appearance
- [ ] Sticky download bar on scroll?
