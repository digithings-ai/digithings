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

## Phase 0 — Canon (this branch) ✅

1. Lock BLEND.md as approved.
2. Promote tokens: `--r-*` → `0`, `--font-display` → mono stack, section rhythm sparse-leaning.
3. Restyle design-reference foundations + family sheets to the composite grammar.
4. Keep product apps compiling; visual drift where they already consume `--r-*` / `--font-display` is expected and intentional — Phase 2/3 clean local fights.

## Phase 1 — Shared React/CSS layer (started on this branch)

Sweep `@digithings/web` hardcoded `border-radius: 999px` on chrome (buttons, chips, tabs, toasts). **Keep** true circles (spinners, live dots, avatars) at `999px`. Align control “dress” axis with fill-vs-outline, not pills. Loud primary → ink/paper fill in `.ctl-btn-ref--primary` / reference `.btn-primary`.

## Phase 2 — Marketing sites

digithings-web + digiquant-web: drop Fraunces hero overrides, hero → claim+install / sparse proof, white rect CTAs, remove soft-radius local CSS.

## Phase 3 — Product apps

digichat (shadcn radius + rose livery kept as accent-only), olympus (retire `.glass-card`), twelve-x / FX Hub (replace `rounded-*` utilities with hairline zero-radius panels).

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
