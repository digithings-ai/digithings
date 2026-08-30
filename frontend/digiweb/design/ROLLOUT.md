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
| digithings.ai | `frontend/digithings-web/` | Phase 2 |
| digiquant.io | `frontend/digiquant-web/` | Phase 2 |
| digichat | `frontend/digichat/` | Phase 3 |
| olympus + FX Hub (twelve-x) | `frontend/olympus/` | Phase 3 |

Same atoms everywhere: **radius 0 · mono voice · white/ink loud CTA · tonal slabs · `//` kickers · sparse marketing / instrument dashboards**.

## How consumption works

digiweb is a **shared library**, not a screenshot to copy. Live surfaces wire:

1. `@digithings/design/tokens.css` — palette, type, radius, section rhythm
2. `@digithings/web` React primitives + family CSS — NavShell, Button, Card, TabStrip, chat, finance, …

So the design-reference + `@digithings/web` restyle **is** the product restyle for every import. Phases 2–3 exist only to **strip product-local fights** that still override the library: Fraunces/`--serif` in marketing `globals.css`, digichat shadcn `--radius-*` / local `@theme`, olympus `.glass-card`, page-level `rounded-*` that never went through a shared component.

Do not invent a second design system per product. If a landing needs a new block, add it to the reference first, then import it.

## Phase 0 — Canon (this branch) ✅

1. Lock BLEND.md as approved.
2. Promote tokens: `--r-*` → `0`, `--font-display` → mono stack, section rhythm sparse-leaning.
3. Restyle design-reference foundations + family sheets to the composite grammar.
4. Keep product apps compiling; visual drift where they already consume `--r-*` / `--font-display` is expected and intentional — Phase 2/3 clean local fights.

## Phase 1 — Shared React/CSS layer ✅ (this branch)

Sweep `@digithings/web` hardcoded pills and shadcn `--radius-*` fallbacks on chrome (buttons, chips, tabs, cards, toasts). **Keep** true circles (spinners, live dots, avatars, radios, slider thumbs). Align every dress axis (reference *and* chat) with fill-vs-outline, not pills. Loud primary → ink/paper fill in `.ctl-btn-ref--primary`, `.ctl-btn-chat--default`, and reference `.btn-primary`.

Product-local `--radius-*` in digichat no longer wins on shared classes — shared sheets pin `border-radius: 0`.

## Phase 2 — Marketing sites (strip local overrides)

digithings-web + digiquant-web already import NavShell / tokens. Remaining work is **not** a second restyle — drop Fraunces hero overrides, local `rounded-[…]`, and any CSS that fights `--font-display` / `--r-*`. Heroes that are still hand-rolled should be swapped to shared claim+install grammar.

## Phase 3 — Product apps (strip local overrides)

digichat (local shadcn `--radius` / `@theme` leftovers), olympus (retire `.glass-card` call-site class), twelve-x / FX Hub (replace leftover `rounded-*` utilities that never went through `@digithings/web`). Shared primitives they already import pick up Phase 1 automatically.

## Non-goals per phase

- Do not invent a second design system per product.
- Do not reintroduce pills “for friendliness.”
- Module liveries stay for **accent identity only** — never primary CTA fill.
- Money colours (`--up`/`--down`) stay fenced.

## Acceptance (whole program)

- [ ] design-reference `/` and `/iterate` composite match BLEND v0.1
- [ ] `tokens.css` ships radius 0 + mono display
- [ ] digithings.ai / digiquant.io heroes use claim+install grammar
- [ ] digichat transcript + chrome are zero-radius mono (composer may keep sans island if still needed)
- [ ] olympus + FX Hub: no glass, no pill chrome, same type stack
- [ ] `scripts/check_frontend_canon.py` still green; update allowlists only with comment

## How to run the next wave

One PR per phase (or per product in Phase 2/3). Always start from design-reference visual check at `http://127.0.0.1:4013`, then the target app.
