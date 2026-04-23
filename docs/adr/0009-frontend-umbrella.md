# ADR-0009 — Frontend umbrella (monorepo `frontend/*` with shared design workspace)

- **Status:** Accepted (2026-04-19)
- **Supersedes (in part):** [ADR-0002 — domain unification](0002-domain-unification.md)
- **Related epic:** [#254](https://github.com/digithings-ai/digithings/issues/254)
- **Parent epic:** [#235](https://github.com/digithings-ai/digithings/issues/235)

## Context

The DigiThings repo shipped three web surfaces in three different
hybrid states:

1. `website/` — committed to the monorepo, deployed to `digithings.ai`
   via `static.yml`.
2. `website/digiquant/` — a sibling subdirectory in the same tree,
   reserved for `digiquant.io`.
3. `digichat/` — **gitignored** in the monorepo
   (`/.gitignore: /digichat/`), present only as a local working tree on
   maintainer laptops. `.github/workflows/ci.yml` carried a comment
   describing `digichat` as a "separate deployment repo" that was never
   actually created. `digithings-ai/digichat` does not exist on GitHub.

Concurrently, Atlas took the opposite approach: the `digiquant-atlas`
research project lives inside the monorepo under `apps/digiquant-atlas/`,
with its Next.js frontend at `apps/digiquant-atlas/frontend/`.

Epic [#235](https://github.com/digithings-ai/digithings/issues/235) introduced
a shared design system (tokens, component primitives, starfield module)
under `website/`. Three of the five subtasks landed (#244, #245, #246).
The remaining two — [#240](https://github.com/digithings-ai/digithings/issues/240)
(digichat adopts shared tokens) and
[#241](https://github.com/digithings-ai/digithings/issues/241)
(digichat `/embed` route) — blocked immediately:

- #240 wants digichat's `globals.css` to `@import` the design tokens,
  but digichat is a different repo. Cross-repo import = publish to npm or
  vendor a checked-in copy with drift detection. Either is expensive for a
  2-person operation.
- #241 wants a new Next.js route in digichat, but digichat isn't even
  tracked in the repo where the planning issue lives.

## Decision

Unify all DigiThings web frontends under a single `frontend/` umbrella
in the existing monorepo, backed by an npm workspace and a
`@digithings/design` package.

```
digithings-ai/digithings/
├── digigraph/ digiquant/ digisearch/ digiclaw/ digismith/ digikey/ digibase/
├── frontend/
│   ├── design/             # @digithings/design workspace package
│   ├── website/                   # digithings.ai
│   ├── digiquant-web/             # digiquant.io
│   └── digichat/                  # chat.digithings.ai (Next.js)
├── apps/
│   └── digiquant-atlas/
│       └── frontend/              # Atlas — joins workspace in place
├── package.json                   # workspaces: ["frontend/*", "apps/*/frontend"]
└── [rest unchanged]
```

Atlas's research-project shell (`apps/digiquant-atlas/`) is intentionally
*not* relocated — `agents/`, `cowork/`, `data/`, and `docs/` are more than
a web frontend. Only its `frontend/` subpackage joins the workspace.

## Consequences

### Positive

- **Token sync is free.** A single source of truth at
  `frontend/design/tokens.css` is consumed by every surface via
  workspace resolution. No HTTPS drift checks, no `npm publish` loop.
- **Atomic cross-surface changes.** A design edit + its consumers
  update in one PR with one review. Previously this would have required
  coordinating three repos.
- **Existing primitives already wired.** Project #1, `make task`, the
  `module/*` branching model, the `batch` skill, scoring gates, the
  pre-push hook, and the PR automation are all single-repo tools. The
  umbrella doesn't require new machinery.
- **CI alignment.** `digichat-test.yml` finally activates, gated on
  `frontend/digichat/**` + `frontend/design/**`.
- **History preserved.** All moves used `git mv` where possible; only
  the digichat import is from a fresh working tree (its prior 3-commit
  local history is acceptable loss).

### Negative

- **Larger repo.** `frontend/digichat/` adds ~100 tracked files; root
  `package-lock.json` will appear on first `npm install`.
- **Workflow churn.** Outstanding feature branches need to rebase /
  resolve path changes once this lands. Mitigation: scheduled ahead of
  any large in-flight frontend branches.
- **Convention overhead.** Contributors must know the layout (workspace
  names, relative-path rules for the static sites, how Atlas's frontend
  is wired in place). Documented in `CLAUDE.md` and `AGENTS.md`.

### Deferred

- Actual `@import` of design tokens into
  `frontend/digichat/src/app/globals.css`. Tracked by #240. The design
  `tokens.css` and shadcn both use `--accent` (as distinct semantic tokens);
  resolving that is a substantive design decision that belongs with #240,
  not this structural reorg.
- digichat `/embed` route. Tracked by #241; the saved reference
  implementation at `/tmp/embed-unit-241/` is reusable as-is against
  `frontend/digichat/src/app/embed/`.
- Atlas adopting the design. Scope only wires the workspace
  reference (`@digithings/design: "*"`); token adoption is a
  follow-up against `apps/digiquant-atlas/frontend/`.
- Physical relocation of Atlas frontend to `frontend/atlas/`. Keeping
  it nested under the research project is fine for now.
- Digiquant.io separate Pages deploy. The current `static.yml` only
  publishes `frontend/digithings/`. Parallel workflow for
  `frontend/digiquant/` → digiquant.io is tracked under epic #9.

## Alternatives considered

1. **Three separate repos** (`digithings`, `digiquant-web`, `digichat`)
   with shared design as an npm-published package. Rejected:
   triples the process surface (branches, CI, issues, release cadence)
   for a 2-person operation; cross-repo PRs for every
   design-visible change.
2. **Keep digichat out** (status quo). Rejected: the parent epic #235's
   work (#240, #241) was already blocked on this decision. Deferring
   just bounces the same decision when the next cross-surface epic lands.
3. **Git submodule for digichat**. Rejected: submodules add operational
   friction (explicit `--recurse-submodules`, forgotten updates, no
   monorepo-wide CI reach) without the benefit of a truly
   independent-release cycle, which isn't needed here.

## Implementation notes

- npm (not pnpm) — matches the pre-existing `digichat/package-lock.json`.
- Static sites reference the design via `../design/…`
  relative paths. Published via a `dist/` assembly step in `static.yml`
  that copies both `frontend/digithings/` and `frontend/design/`
  into the Pages artifact.
- `frontend/digichat/package.json` declares `@digithings/design`
  as a workspace dependency, but `globals.css` does not yet `@import` it
  (see "Deferred").
- `apps/digiquant-atlas/frontend/package.json` same — reference only.
- All workflow path filters and `make` targets updated
  (`static.yml`, `digichat-test.yml`, `ci.yml`, `Makefile`,
  `scripts/generate-qr.py`).

## Amendment to ADR-0002

ADR-0002 described a two-domain plan (`digithings.ai` + `chat.digithings.ai`)
and implied the chat surface lived in its own repo. That implication is
superseded here: the *domain* unification is preserved, but the *repo*
split is reversed. Both surfaces now ship from this monorepo's
`frontend/` umbrella.
