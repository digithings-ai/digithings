---
name: digiweb
description: The pass-through for all digithings.ai / digiquant.io frontend work. Before building any web/UI surface, consult the digiweb design suite — reuse a standardized component from the reference, or add the new pattern there first. Triggers on frontend/UI/component/page/landing/marketing work for digithings or digiquant, on "design reference", and on "/digiweb".
---

# digiweb — frontend design suite pass-through

digiweb (`frontend/digiweb/`) is the **single source of truth** for digithings
web UI. Every frontend surface for **digithings.ai**, **digiquant.io**,
**digichat**, and **olympus** is assembled from the same tokens, livery, motion
laws, and components living here. Your job on any frontend task: **reuse before
you invent, and invent *here* before you consume.**

## When this applies

Any task that creates or changes a web/UI surface for digithings or digiquant —
a page, section, component, landing/marketing block, dashboard widget, chart,
form, chrome. If you're about to write JSX/CSS for a product frontend, start
here.

## Steps

1. **Read the index.** Open `frontend/digiweb/MANIFEST.json` — a machine index of
   every reusable component: `name`, `id`, `path`, `family`, one-line `summary`.
   Skim the family that matches the task (foundations, controls, layout-patterns,
   typography, data, finance, effects, chrome, terminal, chatbot, symbols,
   account).

2. **Find the closest existing pattern.** Match the task to a component by family
   + summary. When in doubt, open the reference live
   (`npm run dev --workspace design-reference` → `http://127.0.0.1:4013`) and
   browse the family page.

3. **Reuse it — copy the grammar, not just the pixels.** Bring the component's
   structure, class prefixes, and token usage into the product app. Do **not**
   fork a divergent copy or hardcode values it takes from tokens.

4. **If nothing fits, add the pattern to the reference *first*.**
   - Build it in `reference/components/` (`"use client"` only if it needs
     state/effects) with a leading `/** … */` docblock (the manifest reads it).
   - Styles in the owning page's `<family>.css` with a unique class prefix.
   - Place it in `reference/app/<family>/page.tsx` using the section grammar.
   - From `reference/`: `npx tsc --noEmit` and `npx eslint .` clean; verify live.
   - Regenerate the index: `node frontend/digiweb/scripts/build-manifest.mjs`.
   - *Then* consume it in the product app.

## The canon (never violate)

- **Tokens, never literals.** Colours come from `@digithings/design/tokens.css`
  (`--ink`, `--surface`, `--bg`, `--hair`, `--accent`, `--up`/`--down`). Use
  token-backed Tailwind utilities or semantic classes — never ad-hoc hex/rgb.
- **Monochrome is the default livery;** colour is opt-in per product via a scope
  class (`accent-digiquant`, …). `atlas`/`hermes`/`kairos` are backend langgraph
  names, not coloured products.
- **Money colours** (`--up`/`--down`) are P&L-only and never follow a livery.
- **One motion moment per surface;** always honour `prefers-reduced-motion`
  (render the final state). Import Motion as `m` from `motion/react` (LazyMotion
  is app-wide; no `layout`/`layoutId`). Content must read without JS.
- **Charts** use TradingView Lightweight Charts, themed from tokens, `autoSize`
  on; no custom candle renderers.

Full detail: `frontend/digiweb/README.md` and `frontend/digiweb/reference/README.md`.
