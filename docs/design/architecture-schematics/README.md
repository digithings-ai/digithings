# Architecture schematics

Inspiration only. A later pass should make the diagrams richer. Enrich the graphs and animations that already exist. Do not start a new product direction.

These clips are a visual reference. Do not copy names, branding, or prices out of them.

## What each clip contributes

### `dark-terminal-wireframe.mp4`

Dark monospace terminal. 1px wireframe. The graph is fully drawn. Telemetry motion. One-line status bar. No draw-on. No particles.

### `vertical-step-stack.mp4`

Vertical step stack. Orthogonal arrows. Loop until done. Legend. Numbered list. Receipt log and counters. Amber or warm for the active step. Blue for a model step or a side step. Green for ok. Red only for a real fallback.

### `ascii-wire-status.mp4`

ASCII boxes. Dotted edges. Marks traveling the wires. Status flipping from running to ok. A footer counting active threads.

## Where the groundwork lives

- `packages/ui` — `TerminalSchematic` in `packages/ui/src/components/diagrams/TerminalSchematic.tsx`
- `apps/digithings-web` — the three app examples in `apps/digithings-web/lib/appFlows.ts` and `apps/digithings-web/components/landing/AppFirstSection.tsx`
- `apps/digiquant-web` — the four workflow cards in `apps/digiquant-web/app/_bands/pipeline.tsx` and `apps/digiquant-web/components/pipeline/workflow-graph.tsx`

Digi names stay lowercase in prose.
