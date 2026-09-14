# digiweb blend lock — utilitarian terminal

**Status:** v0.1 **approved** for promotion · Round 1 locked 2026-08-30  
**North star:** utilitarian terminal simplicity — mono voice, zero corners, sparse air, white loud CTA, diegetic install proof.

Canon promotion: [`ROLLOUT.md`](ROLLOUT.md) · live check: design-reference `/iterate`

This file is the **human preference ledger**. Live picker: design-reference `/iterate`.  
Gallery CSS is `uv-`-prefixed and does **not** ship to product apps until we promote winners into `DESIGN.md` + `tokens.css`.

## Inspiration set

| Source | Role in the blend |
|--------|-------------------|
| digiweb Instrument Panel | Spine — tokens, three colour domains, hairline elevation, money fencing |
| [herdr.dev](references/herdr.dev.md) | Zero radius, claim+install hero, sharp fields, diegetic terminal |
| [agentmail.to](references/agentmail.to.md) | White rect CTA, sparse nav/density, bracket docs control |
| [omarchy.org](references/omarchy.org.md) | Mono-everything voice |
| Cursor / Graphite / xAI | Section discipline / optional motion / `//` kickers |

## Round 1 — raw picks (your preference)

| Axis | Pick | Inspired by |
|------|------|-------------|
| Control radius | Zero | herdr |
| Card / panel radius | Zero slab | herdr |
| Type voice | Mono everything | omarchy / xAI |
| Primary CTA | White rect | agentmail / xAI |
| Nav chrome | Sparse ghost | agentmail |
| Section kicker | // comment | digiweb / xAI |
| Hero composition | Claim + install | herdr |
| Density / spacing | Sparse | agentmail |
| Surfaces | Soft card | digiweb current |
| Stat strip | Quiet row | digiweb current |
| Form inputs | Sharp field | herdr terminal |
| Secondary docs control | Bracket corners | agentmail |

These are a **starting point**, not absolute law. Below is the consistency pass that turns preference into a cohesive system.

---

## Consistency review (round 1)

### What already coheres

- **Zero + zero** (controls and cards) — one radius vocabulary. No pill/rect dual system to maintain.
- **Mono everything + `//` kickers** — same face for claim, body, chrome, and section labels (xAI/omarchy).
- **White rect CTA + sparse ghost nav + bracket docs** — one marketing chrome family (agentmail). Loud = paper fill; quiet = hairline or corner ticks.
- **Claim + install hero + sparse density + quiet stats** — first viewport stays calm; no huge-number strip competing with the curl box.
- **Sharp fields + zero controls** — form language matches button language (herdr terminal).

### Tensions to resolve (not discard)

| Tension | Why it fights | Cohesive resolution |
|---------|---------------|---------------------|
| **Soft card** vs **zero slab** | “Soft” usually means radius; you also picked zero everywhere | Keep **soft = tonal fill** (`--surface` + hairline), drop soft radius. Rename mentally to **tonal slab**. Depth from value step, not roundness. |
| **Mono everything** vs Instrument Serif in shipping `DESIGN.md` | Current canon uses serif for human claims | Round-1 default: **mono for all roles**. Serif becomes an *escape hatch* for rare editorial moments (quotes, legal names) — not marketing H1. |
| **White rect CTA** vs “one loud accent-colored thing” | Old rule spent `--accent` on the primary button | New rule: **loud = ink-on-paper (or paper-on-ink) fill**. `--accent` moves to focus, live/status, links-in-prose, chart identity — never the primary marketing fill. |
| **Sparse density** vs finance/dashboards | Sparse marketing air fights data density | **Two densities by surface:** marketing/docs = sparse; dashboard/tearsheet/terminal scrollback = instrument density. Same radius/type/CTA grammar. |
| **Bracket docs** vs zero radius | Brackets are ornamental corners | Keep — brackets are *structure marks*, not radius. They read as terminal chrome, not soft UI. |

### Cohesive v0.1 rules (locked · promoted)

1. **Radius:** `0` everywhere in marketing and product chrome. No pills. Device bezels may still simulate hardware.
2. **Type:** Geist Mono (or JetBrains Mono on full-terminal surfaces) for display, body, and chrome. Weight 400–500; hierarchy by size/tracking, not bold.
3. **Loud control:** one white (paper) filled rectangle per viewport on dark; dark ink label. Sibling docs control uses bracket corners.
4. **Nav:** few links, ghost/hairline; one filled Login/Install max.
5. **Kicker:** `// section` mono comment — keep.
6. **Hero:** claim + curl/install box + quiet trust meta; optional quiet stat row below the fold or under the install band — never competing in the hero. Quiet stats are **figure-forward**: oversized tabular numerals, tiny uppercase labels (not near-title weight).
7. **Surfaces:** tonal slabs — `--surface` fill, 1px hairline, **0 radius**. Not glass, not soft round cards.
8. **Inputs:** 0–2px (prefer 0), mono value, canvas fill, hairline; focus via accent ring only.
9. **Accent:** phosphor/module colour for focus, live, selected, money-adjacent identity — **not** primary CTA fill.
10. **Density:** sparse section rhythm on landings; instrument rhythm inside dashboards — same atoms.

### Round-1 refinements (post-composite)

| Item | Feedback | Lock |
|------|----------|------|
| Quiet stat strip | Numerals too close in weight/size to labels | **Figure-forward quiet row** — numeral ~2× label optical size; labels shrink + track out |

### Explicit non-goals (for now)

- Do not reintroduce pills “just for buttons.”
- Do not put lavender/violet brand washes (herdr spot) into digiweb liveries.
- Do not synthwave / pixel wordmarks (omarchy nostalgia).
- Do not Inter-as-display (agentmail default we reject).

---

## Promotion status

v0.1 is **promoted** into `DESIGN.md` frontmatter + `tokens.css` + design-reference foundations and an early `@digithings/web` chrome sweep. Product apps (digithings-web, digiquant-web, digichat, dashboard / FX Hub) follow [`ROLLOUT.md`](ROLLOUT.md) Phases 2–3.

The `/iterate` gallery stays as the preference ledger UI (`uv-` CSS only). Further round tweaks edit BLEND first, then re-promote tokens.

Do **not** ship production landings from gallery CSS alone.
