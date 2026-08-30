# digiweb blend lock — utilitarian terminal

**Status:** iterating · **Started:** 2026-08-30  
**North star (proposed):** utilitarian terminal simplicity — basic, sharp, sparse. Prefer hairlines and mono chrome over rounded “advanced UI,” special display fonts, and decorative motion.

This file is the **human preference ledger**. The live picker is the design-reference `/iterate` page (choices persist in `localStorage` as `dr-util-prefs`). When a round of picks lands, copy them here and fold winners into `DESIGN.md` + tokens.

## Inspiration set

| Source | Role in the blend |
|--------|-------------------|
| digiweb Instrument Panel | Spine — tokens, three colour domains, one loud thing, hairline elevation |
| [herdr.dev](references/herdr.dev.md) | Diegetic terminal as hero; sharp/zero radius option; uppercase mono chrome |
| [agentmail.to](references/agentmail.to.md) | Sparse split hero; white filled CTA on dark; live code proof |
| [omarchy.org](references/omarchy.org.md) | Mono-as-voice confidence; light weight; no decoration in chrome |
| Cursor / Graphite / xAI | Existing north stars — still valid; denser motion (Graphite) is optional, not default |

## Direction (working)

- **Fonts:** basic utilitarian — Geist Sans + Geist Mono (or JetBrains Mono for full-terminal surfaces). Serif display becomes *opt-in*, not the default claim voice.
- **Corners:** sharp by default for marketing chrome (0–4px); soft pills only where “actionable” still needs to read instantly — under debate on `/iterate`.
- **Colour:** monochrome resting state; one accent; money colours fenced. No lavender/violet brand wash, no synthwave, no glass.
- **Layout:** one job per section; product/terminal proof over illustration; curl/install and live demos beat feature grids.
- **Motion:** still one moment per surface; magnetic CTAs and scroll theater are opt-in, not foundations.

## Preference ledger

_Fill from `/iterate` after each review round. Values below are the proposed starting picks — not locked._

| Axis | Current digiweb | Proposed start | Your pick | Notes |
|------|-----------------|----------------|-----------|-------|
| Radius — controls | pill `999px` | sharp `2px` / soft `4px` | _open_ | herdr leans 0; agentmail soft |
| Radius — cards | `8/12/16` | `0` marketing / `4` product | _open_ | |
| Type — display | Instrument Serif / Fraunces | Geist Sans 400–500 | _open_ | serif kept for rare human claims |
| Type — body | Geist Sans | Geist Sans | _open_ | |
| Type — chrome | Geist Mono | Geist Mono / JetBrains | _open_ | omarchy = JetBrains everywhere |
| Primary CTA | accent pill | white fill rect on dark **or** ink fill sharp | _open_ | agentmail white; Factory ink |
| Ghost / docs | hairline pill | hairline sharp + optional bracket corners | _open_ | |
| Nav labels | mixed case | uppercase mono tracked | _open_ | herdr |
| Kicker | `// section` mono | keep `//` **or** uppercase tracked | _open_ | |
| Hero | mesh + claim | claim + curl **or** split live proof | _open_ | herdr / agentmail |
| Density | generous section clamp | slightly tighter instrument | _open_ | |
| Surfaces | soft surface cards | flat hairline panels | _open_ | already close |

## How we iterate

1. Open `npm run dev --workspace design-reference` → `/iterate`.
2. For each axis, click the variant you prefer (multi-pick allowed while exploring).
3. Export / paste the ledger into this file.
4. Agent folds locked picks into `DESIGN.md` frontmatter + `tokens.css` in a follow-up PR — not mid-gallery.

Do **not** ship production landings from un-locked gallery CSS. Gallery classes are prefixed `uv-` and live only in the reference app.
