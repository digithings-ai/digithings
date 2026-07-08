# digiquant.io landing — locked design + implementation handoff

This folder is a **design prototype + handoff package** for redesigning the real
`frontend/digiquant-web` app. Nothing here ships; it's the reference to port from.

## The locked design
**`07-scroll-driven.html`** is the approved, final direction (open it in a browser).
It is a self-contained HTML/CSS/JS prototype of the digiquant.io landing page:

- Centered editorial hero — *"A quant hedge fund. In a box you own."* — over a
  **mouse-following animated mesh gradient** (Stripe-style), staggered reveal on load.
- A **scroll-pinned Olympus pipeline**: one continuous, lerp-smoothed horizontal track of
  the **real** Atlas → Hermes → Kairos research phases; engine headings crossfade; each engine
  gets a dwell window; **Kairos is marked "In development."**
- A **vertical tearsheet strategy suite** on the **real** BTC/ETH/SOL Slapper backtests
  (data from `frontend/digiquant-web/public/strategies/index.json`); sticky tearsheet on the
  right swaps as you scroll or click; links to `/strategies/<id>`.
- Lowercase **digiquant** brand + the **QR mark** (the QR encodes `https://digiquant.io`).
- Open-source closing section. No live tape / no live prices (decision below).

`01`–`06` are earlier rejected explorations, kept for history. `qr-digiquant*.svg` are the
generated QR marks (already copied into `digiquant-web/public/favicon-qr*.svg`).

## How to continue
1. Read **`IMPLEMENTATION_PLAN.md`** — the approved plan to port v7 into `digiquant-web`
   (whole site, digiquant-local only, no shared-package edits → digithings.ai untouched).
2. Read **`DESIGN_DECISIONS.md`** — the full decision log (positioning, copy, what was
   rejected and why, the real pipeline phase names, the no-live-prices decision, etc.).
3. Port `07-scroll-driven.html`'s CSS/JS into React client components under
   `frontend/digiquant-web/components/landing/` and rewrite the pages. Reuse the existing
   design tokens (`@digithings/design`), `Brand`/`_nav.tsx`, the strategies JSON, and
   `components/tearsheet/`.

## Already done (verify, don't redo)
- `digiquant-web/public/favicon-qr.svg` + `-light.svg` now encode `https://digiquant.io`.
- `digiquant-web/app/_nav.tsx` `Brand` already renders lowercase `digiquant` + the QR mark.
- `digiquant-web/app/layout.tsx` wires the QR favicon (light/dark). Metadata title still says
  "DigiQuant" — rename to lowercase per the plan.
- `.claude/launch.json` has dev-server configs: `digiquant-web` (4011), `digithings-web` (4012),
  `demos` (4020, static-serves this folder). Run `npm install` in the worktree first.
