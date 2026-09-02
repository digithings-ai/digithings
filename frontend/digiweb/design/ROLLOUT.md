# digiweb utilitarian rollout

**Status:** v0.1 approved for promotion · **2026-08-30**  
**Goal:** one cohesive utilitarian-terminal language across digiweb → every live product surface.

Canon: [`BLEND.md`](BLEND.md) · [`DESIGN.md`](../DESIGN.md) · reference `/iterate`

## End state

| Surface | Path | Follows digiweb tokens + grammar |
|---------|------|----------------------------------|
| design-reference | `frontend/digiweb/reference/` | **Phase 0 — now** |
| `@digithings/design` tokens | `frontend/digiweb/design/tokens.css` | **Phase 0 — now** |
| `@digithings/web` shared sheets | `frontend/digiweb/web/src/styles/` | Phase 1 |
| digithings.ai | `frontend/digithings-web/` | **Phase 2 — this branch** |
| digiquant.io | `frontend/digiquant-web/` | **Phase 2 — this branch** |
| digichat | `frontend/digichat/` | Phase 3 |
| olympus + FX Hub (twelve-x) | `frontend/dashboard/` | Phase 3 |

Same atoms everywhere: **radius 0 · mono voice · white/ink loud CTA · tonal slabs · `//` kickers · sparse marketing / instrument dashboards**.

## How consumption works

digiweb is a **shared library**, not a screenshot to copy. Live surfaces wire:

1. `@digithings/design/tokens.css` — palette, type, radius, section rhythm
2. `@digithings/web` React primitives + family CSS — NavShell, Button, Card, TabStrip, chat, finance, …

So the design-reference + `@digithings/web` restyle **is** the product restyle for every import. Phases 2–3 exist only to **strip product-local fights** that still override the library: Fraunces/`--serif` in marketing `globals.css` (Phase 2, stripped), digichat shadcn `--radius-*` / local `@theme`, olympus `.glass-card`, page-level `rounded-*` that never went through a shared component.

Do not invent a second design system per product. If a landing needs a new block, add it to the reference first, then import it.

## Phase 0 — Canon (this branch) ✅

1. Lock BLEND.md as approved.
2. Promote tokens: `--r-*` → `0`, `--font-display` → mono stack, section rhythm sparse-leaning.
3. Restyle design-reference foundations + family sheets to the composite grammar.
4. Keep product apps compiling; visual drift where they already consume `--r-*` / `--font-display` is expected and intentional — Phase 2/3 clean local fights.

## Phase 1 — Shared React/CSS layer ✅ (this branch)

Sweep `@digithings/web` hardcoded pills and shadcn `--radius-*` fallbacks on chrome (buttons, chips, tabs, cards, toasts). **Keep** true circles (spinners, live dots, avatars, radios, slider thumbs). Align every dress axis (reference *and* chat) with fill-vs-outline, not pills. Loud primary → ink/paper fill in `.ctl-btn-ref--primary`, `.ctl-btn-chat--default`, reference `.btn-primary`, `.cw-btn--primary`, composer send, and `design/site/site.css` `.btn-primary`.

Product-local `--radius-*` in digichat no longer wins on shared classes — shared sheets pin `border-radius: 0`. Native nav `<select>` in the design-reference uses appearance:none + opaque canvas fill so the UA does not paint a pill track.

## Phase 2 — Marketing sites (strip local overrides) ✅ (this branch)

digithings-web + digiquant-web already import NavShell / tokens. This pass dropped Fraunces hero overrides, local `rounded-[…]`, accent-pill CTAs, and CSS that fought `--font-display` / `--r-*`. Heroes keep the existing mesh composition and add the shared `.cmdline` install proof plus one ink/paper `.btn-primary`. Invoice/quote print templates and `/changelog` (tagged GitHub releases via `design/releases.json` + `.changelog-band`) follow the same chrome.

## Phase 3 — Product apps (strip local overrides)

digichat (local shadcn `--radius` / `@theme` leftovers — pinned to 0), olympus
(retired `.glass-card`; dashboard chrome `rounded-*` stripped to slabs;
loud actions ink/paper), twelve-x / FX Hub (hairline slabs). Shared
primitives they already import pick up Phase 1 automatically. Remaining
circles are geometry only (live dots, avatars, spinners).

## Non-goals per phase

- Do not invent a second design system per product.
- Do not reintroduce pills “for friendliness.”
- Module liveries stay for **accent identity only** — never primary CTA fill.
- Money colours (`--up`/`--down`) stay fenced.

## Acceptance (whole program)

- [ ] design-reference `/` and `/iterate` composite match BLEND v0.1
- [x] `tokens.css` ships radius 0 + mono display
- [x] digithings.ai / digiquant.io heroes use claim+install grammar
- [x] digichat transcript + chrome are zero-radius mono (composer may keep sans island if still needed)
- [x] olympus + FX Hub: no glass, no pill chrome, same type stack
- [ ] `scripts/check_frontend_canon.py` still green; update allowlists only with comment

## How to run the next wave

One PR per phase (or per product in Phase 2/3). Always start from design-reference visual check at `http://127.0.0.1:4013`, then the target app.
