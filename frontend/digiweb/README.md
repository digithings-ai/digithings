# digiweb

**The frontend design suite for digithings.** digiweb is the single, central
place all web/UI work for **digithings.ai** and **digiquant.io** passes through:
brainstorm here, copy a standardized component, and add new patterns here so the
reference stays the source of truth. The point is consistency — every product
surface is assembled from the same tokens, livery, motion laws, and components.

> **The rule of the road:** before you build a frontend surface for digithings
> or digiquant, open the reference, find the closest existing pattern, and copy
> its grammar. If nothing fits, build the new pattern *here* first, then consume
> it. Don't invent one-off components in a product app.

## What's in the suite

| Part | Location | Package | Role |
| ---- | -------- | ------- | ---- |
| **reference app** | [`reference/`](reference/) | `design-reference` | The live, browsable showcase — every reusable pattern rendered as working code at `http://127.0.0.1:4013`. Start here. |
| **design tokens** | `frontend/design/` | `@digithings/design` | Colours, type, spacing, motion easings — `tokens.css`. The single palette every surface builds from. |
| **shared components** | `frontend/web/` | `@digithings/web` | The React component layer (Terminal, emblems, graph, ThemeProvider, MotionProvider, module data) consumed across all frontends. |

> The token and component packages are consumed **by package name**
> (`@digithings/design`, `@digithings/web`) everywhere, so they resolve
> regardless of on-disk location. Physically folding them under `digiweb/` is a
> follow-up move gated on a deploy-path review (see [ARCHITECTURE.md](ARCHITECTURE.md)).

## Agent access

digiweb is built to be read by coding agents, not just people:

- **[`MANIFEST.json`](MANIFEST.json)** — a machine-readable index of every
  component in the reference: name, path, family, and a one-line purpose.
  Regenerate it with `node scripts/build-manifest.mjs` after adding a component.
- **The `digiweb` skill** (`/digiweb`) — routes any agent doing digithings /
  digiquant frontend work through this suite: consult the manifest, reuse a
  component, or add a new one here. Authored in
  `agents/sources/skills/digiweb/` and generated into `.claude/` by
  `make agents-init`.

## Run the reference

```bash
npm run dev --workspace design-reference     # http://127.0.0.1:4013
# or the repo's preview tooling: launch config "design-reference"
```

## Conventions

The canon lives with the reference — see
[`reference/README.md`](reference/README.md) for the full page map, the
tokens-never-literals rule, the two-voice type system, the livery
(monochrome-default) model, the motion laws, and the chart house-rules. In
short:

- **Tokens, never literals.** Colours come from `@digithings/design/tokens.css`.
- **Monochrome is the default livery;** colour is opt-in per product.
- **Money colours** (`--up`/`--down`) are P&L-only and never follow a livery.
- **One motion moment per surface;** always honour `prefers-reduced-motion`.
- **Prefer token-backed Tailwind utilities + semantic classes** over ad-hoc CSS
  values, so spacing and colour stay consistent across products.

## Adding a component

1. Build it in `reference/components/` (`"use client"` only if it needs
   state/effects) with a leading `/** … */` docblock describing its purpose —
   the manifest generator reads that block.
2. Put its styles in the owning page's `<family>.css` with a unique class prefix.
3. Place it in `reference/app/<family>/page.tsx` using the section grammar.
4. From `reference/`: `npx tsc --noEmit` and `npx eslint .` clean; check it live.
5. Regenerate the manifest: `node scripts/build-manifest.mjs`.
