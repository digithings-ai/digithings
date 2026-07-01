# Mobile navigation & interactions

**Viewport:** 390×844 (iPhone-class)  
**Verified:** Playwright a11y snapshots + bounding boxes — 2026-06-29  
**Sites:** graphite.com ✓ · cursor.com ✓ · x.ai ✗ (Cloudflare block)

---

## Comparison table

| Aspect | Graphite | Cursor | x.ai |
|--------|----------|--------|------|
| Header height | 62px (+ 48px announcement) | 56px | — |
| Hamburger | "Menu" 28×28 | "Open navigation" 32×32 | — |
| Auth visible in bar | Log in + Sign up | Sign in | — |
| Menu pattern | `dialog` full sheet | Overlay `navigation` | — |
| Backdrop/scrim | Dialog covers page | TBD (open nav) | — |
| Primary CTA in menu footer | Social icons | TBD | — |
| Theme in header | No | No (footer only) | — |
| Touch target min | 28px (menu — tight) | 32px | — |

---

## Graphite — verified behavior

### Header stack

1. **Announcement** (48px): entire bar clickable → "Read more"
2. **Nav bar** (62px): Logo | Log in + Sign up | Menu

### Menu open (`dialog "Navigation"`)

- Position: `box=0,49,390,795` — full width, below announcement+nav top
- Close: top-right 32×32 "Close" button
- Nav items: **50px row height** each
  - Features (expandable `button`)
  - Resources (expandable `button`)
  - Customers, Docs, Pricing, Contact (`link`)
- Footer of dialog:
  - Social row: 28×28 icon buttons (Contact, Slack, GitHub, X, LinkedIn, YouTube)
  - "©2026 Graphite"

### Implications for DigiThings

- Graphite keeps **conversion CTAs in header** on mobile, not only in sheet
- Our pattern (theme + GitHub always visible, primary CTA in sheet footer) is valid but different — document intentional choice in EVOLUTION.md
- Graphite menu rows at 50px exceed our tap comfort — we use ~54px+ padding on sheet links
- **Our scrim** (`dqnav-backdrop`) is an improvement over Graphite's dialog-only dimming when page content bleeds through

---

## Cursor — verified behavior

### Header (closed)

- Height: 56px
- Logo → `/home` (95×24)
- Sign in → `/dashboard` (visible at 285,13)
- Open navigation: 32×32 at far right

### Hero mobile layout

- h1 at y=161, full width 353px
- "Get started" CTA: 138×44 at y=243
- Product demo: starts y=339, height 720px — **dominates viewport below fold**

### Horizontal overflow sections

- Changelog articles: 262px wide, x positions 19, 290, 562, 833 — **horizontal scroll**
- Blog highlights: same pattern
- Testimonials: figure cards ~320px wide in scroll region

### Footer controls

- Theme: 3-button segmented control (System / Light / Dark), ~40×29 each
- Language selector: 111×31 button

### Menu open

- Not fully captured in this pass — re-audit: click `Open navigation` and snapshot link list

---

## x.ai — not verified (Cloudflare)

Automated browser received "Sorry, you have been blocked" on `x.ai`.

**Inferred from fetch + token docs:**

- Outline pills for nav actions
- Capability cards stack vertically
- Code blocks full-width with horizontal scroll
- Stat counters animate on scroll into view

**Manual re-audit:** iPhone Safari pass recommended.

---

## DigiThings mobile nav (our implementation)

Documented for comparison with references:

| Element | Our implementation |
|---------|-------------------|
| Breakpoint | ≤880px hamburger |
| Header | Hamburger · brand · theme · GitHub |
| Backdrop | `dqnav-backdrop` — 68% bg tint + 12px blur, below nav |
| Sheet | Full height below `--dq-nav-h`, solid `--bg` |
| Sheet footer | Ask digichat (DT) / Olympus (DQ) full-width primary |
| Close | Hamburger → X, Escape, backdrop tap, link navigate |
| Body scroll | `overflow: hidden` on open |

**Aligns with:** Cursor utilitarian header; Graphite full-sheet dialog; adds explicit scrim (user-requested).

---

## Scroll behavior on mobile (all sites)

| Site | Pinning | Horizontal scroll | Auto-hide nav |
|------|---------|-------------------|---------------|
| Graphite | Feature sections stack (not pin on mobile) | Case studies, feature icons | No |
| Cursor | None | Changelog, blog, testimonials | No |
| x.ai | None (inferred) | Pricing tables (inferred) | No |

---

## Re-audit checklist

- [ ] Cursor: full mobile menu link list
- [ ] Cursor: pricing page mobile tier layout
- [ ] Graphite: Features expandable submenu contents
- [ ] Graphite: desktop scroll-pin at 1280px
- [ ] x.ai: manual mobile on real device
- [ ] All three: primary button hover/active states (desktop)
