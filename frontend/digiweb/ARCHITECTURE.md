# digiweb — Architecture

digiweb is the **frontend design suite**: the central, agent-readable home for
every reusable web pattern used by digithings.ai and digiquant.io. It is not a
runtime service — it ships no server and no live-trading or auth surface. Its
job is to make frontend work *consistent* by giving people and agents one place
to discover, copy, and extend standardized components.

## Module map

```
frontend/digiweb/
├── README.md              suite overview + the pass-through rule
├── ARCHITECTURE.md        this file
├── MANIFEST.json          generated machine index of every reference component
├── scripts/
│   └── build-manifest.mjs regenerates MANIFEST.json from the reference source
├── design/                @digithings/design — tokens.css + CSS primitives
├── web/                   @digithings/web — shared React component layer
└── reference/             the live showcase app (Next.js 16 / React 19 / Tailwind v4 / Motion)
    ├── app/<family>/       one page per design family (foundations, controls, …)
    ├── components/         the reusable patterns (one file each, docblock-headed)
    └── README.md           the canon: tokens, livery, type, motion, chart rules
```

The three workspaces are consumed **by package name**, so their on-disk location
is irrelevant to resolution — every other frontend imports them the same way:

| Package | Directory | Provides |
| ------- | --------- | -------- |
| `@digithings/design` | `design/` | `tokens.css` — the palette/type/motion tokens every surface uses |
| `@digithings/web` | `web/` | shared React layer (Terminal, emblems, graph, ThemeProvider, MotionProvider, module data) |

### The move touched deploy config

Relocating `design/` and `web/` under `digiweb/` was pure directory bookkeeping
for *resolution* (imports are by package name), but it did touch the **live
deploy path**, all updated in the relocation commit: `scripts/ci_paths.yaml`
(regenerating the `ci.yml` filter block via `scripts/generate_ci_path_filters.py`)
+ the two Cloudflare deploy workflows + `agent-claude-review.yml`,
`scripts/score.py` (skip list + a per-file rule), `scripts/gen-api-vault.ts`
(a relative `../frontend/digiweb/web/...` import), the `frontend/digiweb/design/**`
invariant in `CLAUDE.md`, and doc links checked by `make doc-check`. Consumers
build unchanged.

## MANIFEST.json — the agent index

A generated JSON so any agent (including via MCP filesystem access) can discover
components without reading every file. Shape:

```jsonc
{
  "generatedAt": "<ISO timestamp>",
  "source": "frontend/digiweb/reference",
  "counts": { "components": 0, "described": 0, "families": 0 },
  "families": {
    "<family>": [
      {
        "name": "PortfolioReference",       // exported component
        "id": "portfolio",                   // file basename, -reference stripped
        "path": "reference/components/portfolio-reference.tsx",
        "summary": "…first sentence of the file's /** */ docblock…"
      }
    ]
  }
}
```

Regenerate after adding/renaming a component:

```bash
node frontend/digiweb/scripts/build-manifest.mjs
```

The generator derives structure (name, path, family) from the filesystem and
the family a component is imported into, and the `summary` from the leading
`/** … */` docblock. Components without a docblock appear with `summary: null` —
the generator prints the coverage so gaps are visible and easy to backfill.

## The `digiweb` skill — the routing contract

`agents/sources/skills/digiweb/SKILL.md` (generated to `.claude/skills/` by
`make agents-init`, declared in `agents.yml` under `claude_code_surface.skills`)
tells an agent doing digithings/digiquant frontend work to: (1) read
`MANIFEST.json`, (2) reuse the closest component, (3) if none fits, add the new
pattern to the reference first, then consume it — never invent a one-off in a
product app. Editing the generated `.claude/` copy is forbidden; edit the source
and run `make agents-init` (CI enforces idempotence).

## Extension guide

- **New component** → see [README.md](README.md) “Adding a component”; give it a
  docblock, place it in a family page, regenerate the manifest.
- **New design family (page)** → add `reference/app/<family>/page.tsx` +
  `<family>.css`, register it in the nav (`reference/components/site-nav.tsx`)
  and the contents overview, then update this map and the reference README.
- **New token** → lives in `@digithings/design/tokens.css` (the shared package);
  reference it, never hardcode the literal.

## Build / CI posture

The reference app is **not** built or linted in CI (no workflow references it);
the gate is local — `npx tsc --noEmit` + `npx eslint .` from `reference/`, plus
a live browser check. The suite has no auth, crypto, or live-trading surface, so
the human-gate items in `CLAUDE.md` do not apply to component work here (a
physical relocation of the shared packages, which touches deploy config, does).
