# Deep scan: x.ai

- **URL:** https://x.ai
- **Audit:** 2026-06-29
- **Methods:** Homepage fetch, /api, /news; public token extractions (shadcn xAI kit, getdesign.md, design-bites); Playwright **blocked by Cloudflare** on automated browser

---

## 1. Site map (pages audited)

| URL | Type | Primary CTA |
|-----|------|-------------|
| `/` | Marketing homepage | "Get API Key" / capability Explore links |
| `/api` | Developer API landing | "Get API Key" / "Read Docs" / "Start building" |
| `/api/imagine` | Imagine API pricing | — |
| `/api/voice` | Voice API pricing | — |
| `/news` | News index | "All posts" |
| `/news/*` | Individual posts | "Read More" |
| `/company` | About (inferred) | — |
| `docs.x.ai` | Documentation | External |
| `console.x.ai` | API console | Sign up |

**Note:** Grok consumer app (`grok.com`) is separate surface — not fully audited here.

---

## 2. Global design tokens (inferred)

### Palette (dark-only marketing)

| Token | Value | Role |
|-------|-------|------|
| `--bg-canvas` | `#0a0a0a` or `#1f2228` | page base |
| `--surface-card` | `#191919` | cards |
| `--hairline` | `#212327` / white @ 10% | borders |
| `--text-primary` | `#ffffff` | headings, body |
| `--text-secondary` | muted gray | captions |
| `--focus-ring` | `#2563eb` | rare input focus |
| Accents (illustrations only) | `#ff7a17` sunset, `#7c3aed` dusk, `#c4b5fd` twilight | not in chrome |

**No shadows.** Depth = hairline + surface step only.

### Typography

| Role | Face | Treatment |
|------|------|-----------|
| Display | Geist Mono | up to 96–320px, weight 300, tracking -2px to -2.4px |
| Body / h2 | Universal Sans (Inter-class) | 16–30px, weight 400 |
| Eyebrows / labels | Geist Mono | **UPPERCASE**, +1.4px tracking, 14px |
| Buttons | Geist Mono | uppercase, tracked |
| Code | Mono in API blocks | Python / TS / cURL tabs |

### Radius

| Element | Radius |
|---------|--------|
| Cards | 8px |
| Pills / buttons | 9999px (only interactive shape besides rects) |
| Inputs | 8px + focus ring |

### Spacing

- 8px base grid: 2, 4, 8, 16, 24, 32, 48, 64px
- Card padding: **24px**
- Section vertical: **~64px** desktop

### Motion

- Stat counter scroll animations (300M+ queries, 150K GPUs, etc.)
- Capability card hovers (subtle)
- Agent UI demos animate internally ("Thinking...", file grep list)
- Footer: optional warm gradient bloom (atmospheric exception)

---

## 3. Navigation system

### Global

- Near-black canvas edge-to-edge
- Ghost **outline pills** for most actions (1px white border, transparent fill)
- **One filled white pill** for primary Sign up / Get API Key
- Sparse link count — minimal nav clutter

### Homepage nav (inferred)

- Logo / wordmark
- Links: API, News, Company, Grok
- CTA: Sign up (filled) vs outline secondaries

### Mobile (not Playwright-verified — Cloudflare block)

- Expect: same pill language, stacked capabilities, full-width code blocks
- Re-audit manually on device

---

## 4. Component catalog

### Hero

- Announcement pill: "New — Grok Build Beta" (inferred from fetch)
- h1: "Frontier AI models for everything you build."
- Sub: "Reasoning, code, voice, images, and video. Trained on the world's largest supercluster."
- Interactive teaser cards (chat prompts rotating):
  - "Explain quantum entanglement simply"
  - "Why is the sky blue?"
  - "How do black holes form?"

### Capability card (modality)

Pattern: mini product UI + **"Explore →"**

| Card | Content |
|------|---------|
| Chat | Q&A teaser |
| Code / Build | Agent terminal: file reads, "Thinking...", task list, JWT migration demo |
| Imagine | Image generation explore |
| Voice | Voice modality explore |

**Code agent mock (homepage):**

```
projects/main | 11.60% | ❯ Migrate auth from sessions to JWT
Thinking...
▸ read_file src/middleware/auth.ts  68 lines
▸ grep "session" src/  4 matches
...
| Audit auth middleware  explore [running]
```

### API section band

- h2: "One API. Every modality."
- Sub: "Text, code, voice, images, and video — all through a single unified API."
- CTAs: **Get API Key** · **Read Docs**
- Stats: "1M+ API calls per day" · "<200ms Median latency" · "5+ Model families"
- Code block with **Python / TypeScript / cURL** tabs + Copy button

```python
from xai_sdk import Client
client = Client(api_key=os.getenv("XAI_API_KEY"))
chat = client.chat.create(model="grok-4.3")
```

### Stat counter strip

Large mono numerals with scroll-triggered count-up:

- "300M+ queries processed daily"
- "150K GPUs in [cluster]"
- "mission to understand the universe" (mission statement as stat)

### News card

- Featured hero post: "Introducing /goal" — Jun 22, 2026
- Grid of cards: title + date + one-line dek
- "All posts" link

### Pricing paths (homepage footer section)

Two columns:

**Build on your own**
- Access to all Grok models
- Usage-based pricing
- Auto-increasing rate limits
- Documentation

**Get extra support**
- Dedicated onboarding
- Custom rate limits
- Invoice billing, SSO, audit log, data residency
- **Contact Sales**

### API page (`/api`) components

- Hero: "Build with the most powerful AI models."
- Product grid: "Every modality, one API" — Imagine, Voice cards
- Capabilities list: Text, Code, Voice API, Search, Image/Video, File management
- Quickstart with compatibility note: "compatible with OpenAI and Anthropic SDKs"
- **Models and pricing table** — grok-4.3, grok-build-0.1 with context window + $/M tokens
- Imagine API sub-table (image/video per-resolution pricing)
- Voice API modes table (Realtime, TTS, STT per-unit costs)
- Cloud partner logos: Azure AI Foundry, OCI, Vertex
- Duplicate "Choose how to get started" + news band

### News index (`/news`)

- Featured large card with "Read More"
- Chronological list: title + date + dek (one sentence)
- Dense archive back to 2023 (API Public Beta, Grok-1 open release, etc.)

### Pill button

- Outline: transparent bg, 1px white border, uppercase mono label
- Filled: white bg, dark text — single primary per viewport

### Card

- `#191919` fill, 1px `#212327` border, 8px radius, 24px padding
- No shadow

---

## 5. Page-by-page breakdown

### Homepage `/`

| # | Section |
|---|---------|
| 1 | Hero + modality teasers |
| 2 | Capability demos (Chat, Code, Imagine, Voice) |
| 3 | Developer API band + code sample + stats |
| 4 | Stat counters (scale story) |
| 5 | Latest news |
| 6 | Pricing paths (self-serve vs sales) |
| 7 | Footer |

### API `/api`

| # | Section |
|---|---------|
| 1 | Hero + code |
| 2 | Products (Imagine, Voice) |
| 3 | Capabilities grid |
| 4 | Quickstart |
| 5 | Models pricing table |
| 6 | Imagine + Voice pricing tables |
| 7 | Cloud partners |
| 8 | Get started columns |
| 9 | News |

---

## 6. Scroll & interaction behaviors

| Behavior | Notes |
|----------|-------|
| Counter animations | Stats section |
| Tabbed code | Python / TS / cURL switch |
| Copy button | API code blocks |
| Capability Explore | Links to product areas |
| Chat teaser | May rotate prompts |
| No scroll-pinned marketing | Unlike Graphite |

---

## 7. Copy & IA patterns

### Voice

- **Infrastructure, not consumer:** "Frontier AI models", "supercluster", "production-ready in minutes"
- **Precision:** model version numbers in tables (grok-4.3, grok-build-0.1)
- **Agency for builders:** "Start building in minutes", "One unified API"

### CTA library

| CTA | Context |
|-----|---------|
| Get API Key | API primary |
| Read Docs | Secondary |
| Start building | Quickstart |
| Explore → | Capability cards |
| Contact Sales | Enterprise column |
| All posts | News index |
| Read More | Featured article |

### Section eyebrows

Uppercase mono labels above h2 — e.g. "For developers", "Capabilities", "Quickstart"

### News headline style

Action-oriented: "Introducing /goal", "Grok on Databricks", "Agent Dashboard in Grok Build"

---

## 8. Mobile-specific patterns (inferred)

- Display type scales down from 320px → ~48–80px
- Capability cards stack vertically
- Code blocks horizontal scroll for long lines
- Pricing tables may scroll horizontally or collapse rows
- Pill buttons full-width stack
- Mono eyebrows remain uppercase at smaller size

**Re-audit needed:** manual mobile pass (Cloudflare blocked automation).

---

## 9. Adopt / Adapt / Avoid (DigiThings)

| Adopt | Adapt | Avoid |
|-------|-------|-------|
| Mono uppercase eyebrows | `// section` kickers (already have) | 320px display on dashboards |
| Outline pill secondary actions | Filter chips on twelve-x | Dark-only (we ship light mode) |
| API band + copy-paste code | digikey token exchange docs | Zero decoration on **landings** (keep mesh) |
| Stat counters with real metrics | OSS download counts when available | Fake GPU counts |
| Modality capability cards | DigiGraph / DigiChat / DigiQuant / DigiSearch | Pill-only buttons for data tables |
| Pricing tables with units | digiquant API if/when priced | Pure black `#000` |
| News/changelog archive | GitHub releases blog | — |

---

## 10. Sources & limitations

- shadcn.io xAI design kit (token extraction)
- getdesign.md / explainx.ai DESIGN.md snapshots
- Live fetch: `/`, `/api`, `/news`
- **Playwright:** blocked — mobile nav not verified
- Re-audit with manual device or residential IP for interaction states
