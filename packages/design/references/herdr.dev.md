# Reference scan: herdr.dev

- **URL:** https://herdr.dev
- **Product:** Agent runtime — keeps coding-agent terminals alive across disconnects
- **Stack (observed):** Astro + custom CSS; ink/paper dual theme
- **Last audited:** 2026-08-30
- **Refero Styles:** not present — closest library matches: Warp, dope.security, Hyperstudio, Factory

---

## 1. First impression

Herdr is **utilitarian terminal maximalism**. The product *is* the hero: a live multi-pane agent layout, not a lifestyle mock. Marketing chrome is sharp (often zero-radius), uppercase mono labels, one spot accent (lavender in ink mode), and a named dual ground — **ink** / **paper**.

---

## 2. What to steal for digiweb

| Pattern | Herdr does | Digiweb adopt / adapt / avoid |
|---------|------------|-------------------------------|
| Diegetic product hero | Real terminal panes, clickable sidebar | **Adopt** for digichat / digithings agent surfaces |
| Ink / paper dual ground | Named modes, shared token roles | **Adapt** — keep our `[data-theme]`, optionally rename copy to ink/paper |
| Zero / near-zero radius | `--radius-*: 0` on marketing chrome | **Adapt** as a *marketing option* in the iterate gallery — not forced on finance cards yet |
| Uppercase tracked nav | 11.5px, `.07em` tracking | **Adopt** for mono chrome labels |
| Spot accent only on action | Lavender for selection / CTA hover | **Avoid** as a second brand hue (collides with digivault); keep one accent |
| Huge condensed display | Archivo 900, clamp to ~132px | **Avoid** shouting weight 900 — prefer weight 400–500 utilitarian |

---

## 3. Tokens (observed)

**Ink mode:** `--bg #17171a` · `--ink #eae8ee` · `--spot #cba6f7` · hairlines `#26262b` / `#35353d` · grid underlay

**Paper mode:** `--bg #efece5` · `--ink #15140f` · `--spot #8839ef`

**Type:** Archivo (display) · Inter (body) · JetBrains Mono (chrome)

**Radius:** marketing surfaces often `0`; terminal mock keeps its own radii

---

## 4. One-line lesson

> Show the work running. Chrome stays sharp and quiet; the terminal panel carries the brand.
