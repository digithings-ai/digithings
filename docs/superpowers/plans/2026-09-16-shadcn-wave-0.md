# shadcn Wave 0 — Token Bridge + Vendored Package (Proof of Chain) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Stand up the shadcn foundation inside `@digithings/web` — the token bridge and the package-level vendored UI set — and prove the chain end-to-end in the reference app: stock `npx shadcn add` components render in the Instrument-Panel skin with zero per-component restyle.

**Architecture:** One vendored set lives in `cloudflare/digiweb/web` (`src/ui/`, generated on the Base UI base with the owner's `buFyyjQ` preset folded into `components.json`), exported as `@digithings/web/ui`. A token bridge inside `web-theme.css`'s single `@theme inline` block maps every shadcn CSS variable onto `@digithings/design` tokens, so components inherit radius-0 / mono / ink-primary / hairline with no per-component CSS. The reference app consumes the package set via an `@source` line and a proof route.

**Tech Stack:** shadcn CLI (latest; Base UI base, `lyra` style), Tailwind v4 (`@theme inline`, `source(none)`), Next 16.2.4 (reference app), vitest 4 (+ `renderToStaticMarkup`, no testing-library), `@digithings/design` tokens.

**Spec:** `docs/superpowers/specs/2026-09-16-shadcn-migration-design.md` (§3.1, §3.2, §5 Wave 0)

**Epic:** [#4206](https://github.com/digithings-ai/digithings/issues/4206) — every PR from this plan lands into `develop` referencing it.

## Global Constraints

- Worktree: `/private/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/digichat-build-2.0` (post-rename tree; the main checkout is stale). All paths below are relative to the repo root inside that worktree.
- `web-theme.css` is the ONLY `@theme` block in the system and MUST stay `@theme inline` (plain `@theme` freezes vars at `:root` and breaks scoped liveries). Never add a second `@theme` block.
- Import order canon: `tailwindcss` → `@digithings/design/tokens.css` → site sheets `layer(components)` → `web-theme.css` → family sheets.
- Every package component rendered by an app needs an explicit `@source` line in that app's globals.css (Tailwind never scans package sources; failure is silent).
- `data-theme` on `<html>` is authoritative; `.dark`/`.light` mirror FROM the attribute, never reverse.
- DESIGN.md laws are non-negotiable in the result: radius 0 on all chrome, mono everywhere, loud = ink/paper (never accent fill), hairline borders, flat by default (shadow only for floating overlays), `--up`/`--down` fixed literals.
- No new app-local CSS class families (`scripts/check_frontend_canon.py` census); no app-local primitives; no new runtime dependencies beyond what the shadcn CLI generates (Base UI, CVA, clsx, tailwind-merge, lucide are already deps).
- shadcn is **Base UI pinned** (owner decision §9 Q2): re-add the whole set on Base UI, no mixed bases.
- Font: **JetBrains Mono** (owner decision §9 Q1) — Wave 0 only carries it in `components.json`/preset; the app-level font swap is Wave 1.
- Tests: vitest. `@digithings/web` asserts with `renderToStaticMarkup` — no testing-library.
- The `(chatbot)` family in reference/ is out of scope and its `@source not` exclusion stays; DigiChat/digichat-ui is untouched.
- Do not push any branch until Task 7.

**Files touched overall:**
- Modify: `cloudflare/digiweb/web/tsconfig.json`, `cloudflare/digiweb/web/package.json`
- Create: `cloudflare/digiweb/web/vitest.config.ts`, `cloudflare/digiweb/web/components.json`, `cloudflare/digiweb/web/src/lib/utils.ts` (+test), `cloudflare/digiweb/web/src/ui/*` (+barrel), `cloudflare/digiweb/reference/app/(gallery)/ui/page.tsx`
- Modify: `cloudflare/digiweb/web/src/styles/web-theme.css` (+contract test), `cloudflare/digiweb/reference/app/globals.css`
- Delete: `cloudflare/digiweb/reference/components/ui/{avatar,button,collapsible,dialog,skeleton,textarea}.tsx` (6 verified-dead files; `tooltip.tsx` + `dot-matrix.tsx` shim stay — load-bearing for `gallery-thread.source.test.ts`)
- Docs: `cloudflare/digiweb/MIGRATION.md`, `cloudflare/digiweb/ARCHITECTURE.md`, `cloudflare/digiweb/MANIFEST.json`

---

### Task 1: Package plumbing — `@/*` alias, vitest alias, `cn()`

**Files:**
- Modify: `cloudflare/digiweb/web/tsconfig.json`
- Create: `cloudflare/digiweb/web/vitest.config.ts`
- Create: `cloudflare/digiweb/web/src/lib/utils.ts`
- Test: `cloudflare/digiweb/web/src/lib/utils.test.ts`
- Modify: `cloudflare/digiweb/web/package.json` (add `typecheck` script)

**Interfaces:**
- Consumes: `clsx`, `tailwind-merge` (already in `web/package.json` deps).
- Produces: `cn(...inputs: ClassValue[]): string` from `@/lib/utils` (all vendored `src/ui/*` files import exactly this path); `@` alias → `cloudflare/digiweb/web/src` for both `tsc` and vitest.

- [ ] **Step 1: Add the alias to tsconfig**

Edit `cloudflare/digiweb/web/tsconfig.json` compilerOptions to add (keep every existing key as-is):

```json
"baseUrl": ".",
"paths": { "@/*": ["./src/*"] }
```

- [ ] **Step 2: Create the vitest alias config**

Create `cloudflare/digiweb/web/vitest.config.ts` (`shadcn add` writes `@/lib/utils` imports; tests resolve them through this alias):

```ts
import path from "node:path";
import { defineConfig } from "vitest/config";

export default defineConfig({
  resolve: {
    alias: { "@": path.resolve(__dirname, "src") },
  },
  test: { environment: "node" },
});
```

- [ ] **Step 3: Write the failing test**

Create `cloudflare/digiweb/web/src/lib/utils.test.ts`:

```ts
import { describe, expect, it } from "vitest";
import { cn } from "./utils";

describe("cn", () => {
  it("merges conflicting tailwind utilities (last wins)", () => {
    expect(cn("p-2", "p-4")).toBe("p-4");
  });

  it("keeps non-conflicting classes", () => {
    expect(cn("text-ink", "rounded-none")).toBe("text-ink rounded-none");
  });
});
```

- [ ] **Step 4: Run test to verify it fails**

Run: `npm --workspace @digithings/web run test -- src/lib/utils.test.ts`
Expected: FAIL — cannot resolve `./utils`.

- [ ] **Step 5: Create `cn()` (identical to the reference app's copy)**

First read `cloudflare/digiweb/reference/lib/utils.ts` and copy its body verbatim; it must be this shape:

```ts
import { clsx, type ClassValue } from "clsx";
import { twMerge } from "tailwind-merge";

export function cn(...inputs: ClassValue[]) {
  return twMerge(clsx(inputs));
}
```

Write it to `cloudflare/digiweb/web/src/lib/utils.ts`.

- [ ] **Step 6: Add the `typecheck` script**

In `cloudflare/digiweb/web/package.json` scripts add:

```json
"typecheck": "tsc --noEmit"
```

- [ ] **Step 7: Verify both pass**

Run: `npm --workspace @digithings/web run test -- src/lib/utils.test.ts && npm --workspace @digithings/web run typecheck`
Expected: 2 passed; tsc exit 0.

- [ ] **Step 8: Commit**

```bash
git add cloudflare/digiweb/web/tsconfig.json cloudflare/digiweb/web/vitest.config.ts cloudflare/digiweb/web/src/lib/utils.ts cloudflare/digiweb/web/src/lib/utils.test.ts cloudflare/digiweb/web/package.json
git commit -m "feat(digiweb): shadcn package plumbing (@/* alias, vitest alias, cn) — wave 0"
```

---

### Task 2: `components.json` — Base UI base + owner preset

**Files:**
- Create: `cloudflare/digiweb/web/components.json`

**Interfaces:**
- Consumes: nothing at runtime.
- Produces: the exact config the `shadcn` CLI reads when run inside `cloudflare/digiweb/web` — `add` writes components to `@/ui` (i.e. `src/ui/`), utils to `@/lib/utils`.

- [ ] **Step 1: Probe the current CLI schema in a scratch dir (no guessing)**

```bash
rm -rf /tmp/shadcn-probe && mkdir -p /tmp/shadcn-probe && cd /tmp/shadcn-probe
npx shadcn@latest init --base base --preset lyra --no-monorepo --css-variables -y -t next
cat components.json
```

Record the generated file. The base selector (`"base": "base"` or equivalent key) and `style` value MUST be copied from this probe verbatim — the schema is CLI-authoritative, not from this plan.

- [ ] **Step 2: Write the package config**

Create `cloudflare/digiweb/web/components.json` with the probe's keys, adjusted to the library layout (this is the shape as of 2026-09-16; reconcile against the probe first, probe wins):

```json
{
  "$schema": "https://ui.shadcn.com/schema.json",
  "style": "lyra",
  "base": "base",
  "rsc": true,
  "tsx": true,
  "tailwind": {
    "config": "",
    "css": "src/styles/web-theme.css",
    "baseColor": "neutral",
    "cssVariables": true,
    "prefix": ""
  },
  "iconLibrary": "lucide",
  "aliases": {
    "components": "@/components",
    "utils": "@/lib/utils",
    "ui": "@/ui",
    "lib": "@/lib",
    "hooks": "@/hooks"
  },
  "registries": {
    "@assistant-ui": "https://r.assistant-ui.com/styles/{style}/{name}.json"
  }
}
```

- [ ] **Step 3: Verify the CLI resolves the config**

```bash
cd cloudflare/digiweb/web
npx shadcn@latest add button --dry-run
```

Expected: planned output includes `src/ui/button.tsx`; no writes. If the CLI refuses inside a non-Next package, run the same `add` inside a scratch Next app with this `components.json` copied in and copy the generated `src/ui/*.tsx` into the package (still no hand-written components).

- [ ] **Step 4: Commit**

```bash
git add cloudflare/digiweb/web/components.json
git commit -m "feat(digiweb): shadcn components.json (Base UI base, lyra preset) — wave 0"
```

---

### Task 3: The token bridge in `web-theme.css`

**Files:**
- Modify: `cloudflare/digiweb/web/src/styles/web-theme.css` (inside the existing `@theme inline` block, lines 16–47)
- Test: `cloudflare/digiweb/web/src/styles/web-theme.test.ts`

**Interfaces:**
- Consumes: semantic tokens from `@digithings/design/tokens.css` (`--bg`, `--ink`, `--surface`, `--surface-2`, `--hair`, `--ink-soft`, `--accent`, `--on-accent`, `--danger`, `--up`, `--down`, `--warn`).
- Produces: the shadcn token contract every vendored `src/ui/*` component reads — `--color-*` theme vars (Tailwind v4 namespace) and `--radius-*`. No bare `--background`/`--primary` aliases are added in Wave 0 (assistant-ui scopes already declare their own; the Wave 2/3 sweep decides on bare aliases with evidence).

- [ ] **Step 1: Write the failing contract test**

Create `cloudflare/digiweb/web/src/styles/web-theme.test.ts`:

```ts
import { readFileSync } from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const css = readFileSync(path.resolve(__dirname, "web-theme.css"), "utf8");

const chartNames = [
  "--color-chart-1",
  "--color-chart-2",
  "--color-chart-3",
  "--color-chart-4",
  "--color-chart-5",
];

const radiusNames = ["--radius-sm", "--radius-md", "--radius-lg", "--radius-xl"];

describe("web-theme shadcn token contract", () => {
  it("maps every shadcn token onto design tokens", () => {
    const pairs: [string, string][] = [
      ["--color-background", "var(--bg)"],
      ["--color-foreground", "var(--ink)"],
      ["--color-card", "var(--surface)"],
      ["--color-card-foreground", "var(--ink)"],
      ["--color-popover", "var(--surface-2)"],
      ["--color-popover-foreground", "var(--ink)"],
      ["--color-primary", "var(--ink)"],
      ["--color-primary-foreground", "var(--bg)"],
      ["--color-secondary", "var(--surface-2)"],
      ["--color-secondary-foreground", "var(--ink)"],
      ["--color-muted", "var(--surface)"],
      ["--color-muted-foreground", "var(--ink-soft)"],
      ["--color-accent", "var(--accent)"],
      ["--color-accent-foreground", "var(--on-accent)"],
      ["--color-destructive", "var(--down)"],
      ["--color-border", "var(--hair)"],
      ["--color-input", "var(--hair)"],
      ["--color-ring", "color-mix(in srgb, var(--accent) 40%, transparent)"],
    ];
    const contractNames = [
      ...pairs.map(([name]) => name),
      ...chartNames,
      ...radiusNames,
    ];
    for (const name of contractNames) {
      expect(css.match(new RegExp(`${name}\\s*:`, "g"))?.length).toBe(1);
    }
    for (const [name, value] of pairs) {
      expect(css).toContain(`${name}: ${value};`);
    }
  });

  it("flattens shadcn radii to zero (Instrument Panel law)", () => {
    for (const radius of radiusNames) {
      expect(css).toContain(`${radius}: 0;`);
    }
  });

  it("keeps exactly one @theme block (canon)", () => {
    expect(css.match(/@theme\s+inline\s*\{/g)?.length).toBe(1);
  });
});
```

- [ ] **Step 2: Run test to verify it fails**

Run: `npm --workspace @digithings/web run test -- src/styles/web-theme.test.ts`
Expected: FAIL — mappings absent.

- [ ] **Step 3: Add the bridge**

In `cloudflare/digiweb/web/src/styles/web-theme.css`, append these lines INSIDE the existing `@theme inline { … }` block (after `--ease-brand`):

```css
  /* shadcn/ui token contract — Base UI base, lyra preset.
     See docs/superpowers/specs/2026-09-16-shadcn-migration-design.md §3.2 */
  --color-background: var(--bg);
  --color-foreground: var(--ink);
  --color-card: var(--surface);
  --color-card-foreground: var(--ink);
  --color-popover: var(--surface-2);
  --color-popover-foreground: var(--ink);
  --color-primary: var(--ink);
  --color-primary-foreground: var(--bg);
  --color-secondary: var(--surface-2);
  --color-secondary-foreground: var(--ink);
  --color-muted: var(--surface);
  --color-muted-foreground: var(--ink-soft);
  /* Brand --color-accent is intentionally held (owned by the row at the top of
     this block); shadcn's subtle accent role + brand-alias rename defer to the
     Wave 2/3 alias sweep. */
  --color-accent-foreground: var(--on-accent);
  --color-destructive: var(--down);
  --color-border: var(--hair);
  --color-input: var(--hair);
  --color-ring: color-mix(in srgb, var(--accent) 40%, transparent);
  --color-chart-1: var(--ink);
  --color-chart-2: var(--accent);
  --color-chart-3: var(--ink-soft);
  --color-chart-4: var(--up);
  --color-chart-5: var(--warn);
  --radius-sm: 0;
  --radius-md: 0;
  --radius-lg: 0;
  --radius-xl: 0;
```

Note: `--color-primary` is ink/paper, never an accent fill (differs from the reference app's old local bridge at `globals.css` L633–654, which the package bridge supersedes). `--color-chart-*` is the neutral starting ramp; Wave 2's chart audit (spec §9 Q4) owns the final values. The brand `--color-accent` is held — the pre-existing row earlier in the block owns the name; shadcn's subtle "accent" surface role and any brand-alias rename are deferred to the Wave 2/3 alias sweep.

- [ ] **Step 4: Run test to verify it passes**

Run: `npm --workspace @digithings/web run test -- src/styles/web-theme.test.ts`
Expected: 3 passed.

- [ ] **Step 5: Commit**

```bash
git add cloudflare/digiweb/web/src/styles/web-theme.css cloudflare/digiweb/web/src/styles/web-theme.test.ts
git commit -m "feat(digiweb): shadcn token bridge in web-theme.css (@theme inline) — wave 0"
```

---

### Task 4: Vendored set in the package + reference rewire

**Files:**
- Create (CLI-generated): `cloudflare/digiweb/web/src/ui/button.tsx`, `card.tsx`, `dialog.tsx`, `input.tsx`
- Create: `cloudflare/digiweb/web/src/ui/index.ts` (barrel)
- Modify: `cloudflare/digiweb/web/package.json` (exports)
- Modify: `cloudflare/digiweb/web/src/styles/web-theme.css` + `web-theme.test.ts` (Step 8b addendum)
- Modify: `cloudflare/digiweb/reference/app/globals.css` (`@source` line; Step 8b stale-bridge removal)
- Delete: `cloudflare/digiweb/reference/components/ui/` — only the 6 verified-dead files (`avatar`, `button`, `collapsible`, `dialog`, `skeleton`, `textarea`); `tooltip.tsx` + `dot-matrix.tsx` stay
- Test: `cloudflare/digiweb/web/src/ui/ui.render.test.tsx`

**Interfaces:**
- Consumes: `cn` from `@/lib/utils` (Task 1) and the token contract (Task 3); consumers render `Button`/`Card`/`Dialog`/`Input` unmodified — zero per-component styling.
- Produces: `@digithings/web/ui` (barrel export: `Button`, `Card`, `Dialog`, `Input`, plus each component's sub-parts). No `./dot-matrix` export — `DotMatrix` already ships as `./chat/dot-matrix`, and the reference shim re-exports it (load-bearing for `gallery-thread.source.test.ts`).

- [ ] **Step 1: Generate the components on Base UI**

```bash
cd cloudflare/digiweb/web
npx shadcn@latest add button card dialog input -y
```

Expected: `src/ui/button.tsx`, `src/ui/card.tsx`, `src/ui/dialog.tsx`, `src/ui/input.tsx` written with `@/lib/utils` imports. Inspect them: they must NOT import `@radix-ui/*` (Base UI base). If any Radix import appears, the base pin in `components.json` is wrong — fix Task 2 and regenerate.

- [ ] **Step 2: Write the render test**

Create `cloudflare/digiweb/web/src/ui/ui.render.test.tsx`:

```tsx
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";
import { Button, Card, CardContent, Input } from "./index";

describe("vendored ui kit renders server-side", () => {
  it("Button keeps the shadcn data-slot contract", () => {
    const html = renderToStaticMarkup(<Button>Run</Button>);
    expect(html).toContain('data-slot="button"');
    expect(html).toContain("Run");
  });

  it("Card composes parts", () => {
    const html = renderToStaticMarkup(
      <Card>
        <CardContent>body</CardContent>
      </Card>,
    );
    expect(html).toContain('data-slot="card"');
    expect(html).toContain("body");
  });

  it("Input renders with the input slot", () => {
    const html = renderToStaticMarkup(<Input placeholder="ticker" />);
    expect(html).toContain('data-slot="input"');
  });
});
```

- [ ] **Step 3: Run test to verify it fails**

Run: `npm --workspace @digithings/web run test -- src/ui/ui.render.test.tsx`
Expected: FAIL — cannot resolve `./index`.

- [ ] **Step 4: Write the barrel**

Create `cloudflare/digiweb/web/src/ui/index.ts` re-exporting everything the four files export, e.g.:

```ts
export * from "./button";
export * from "./card";
export * from "./dialog";
export * from "./input";
```

(Confirm `dialog.tsx` is client-safe to re-export; it carries its own `"use client"`.)

- [ ] **Step 5: Run test to verify it passes**

Run: `npm --workspace @digithings/web run test -- src/ui/ui.render.test.tsx`
Expected: 3 passed.

- [ ] **Step 6: Retire the dead legacy ui files (partial)**

`DotMatrix` already lives in the package (`web/src/components/chat/DotMatrix.tsx`,
export `./chat/dot-matrix`); the reference `components/ui/dot-matrix.tsx` is a re-export shim and
`gallery-thread.source.test.ts` pins both it and the tooltip parity specimen
(`components/ui/tooltip.tsx`). Delete only the verified-dead files:
`avatar button collapsible dialog skeleton textarea`. Keep `tooltip.tsx` + `dot-matrix.tsx`
(load-bearing for the product guard; their retirement belongs with that guard's owner).
Consumers of the shim (`chatbot-thread-list.tsx`, `cube-matrix-legend.tsx`) stay unchanged.

- [ ] **Step 7: Export the barrel** — add `"./ui": "./src/ui/index.ts"` only.

- [ ] **Step 8: Reference app consumes it** — add `@source "../../web/src/ui";`;
  keep `@source not "../components/ui";` (dir still holds the two survivors).

- [ ] **Step 8b: Reconcile the stale reference bridge (ruled addendum)**

`reference/app/globals.css` still carried a local shadcn token bridge (comment + second
`@theme inline` block) predating the Task 3 package bridge. The package supersedes every row
except `--color-input-background`, so that row was folded into `web-theme.css` (+ contract test
pair) and the stale local block deleted. The keyframes-only `@theme inline` (collapsible) stays.
Effective reference mapping now equals the canon (primary = ink, popover = surface-2,
muted-foreground = ink-soft, destructive = down, ring = 40% accent mix).

- [ ] **Step 9: Verify the full package + reference gates**

```bash
npm --workspace @digithings/web run test
npm --workspace @digithings/web run typecheck
cd cloudflare/digiweb/reference && npm run lint && npm run typecheck
```

Expected: web suite 49 files/327 tests green; web `typecheck` stays pre-existing red (30 errors, 0 in `src/ui/` — see Task 1/4 rulings); reference lint + typecheck 0 errors. The reference dev/build proof is Task 5.

- [ ] **Step 10: Commit**

```bash
git add cloudflare/digiweb/web/src/ui cloudflare/digiweb/web/src/styles/web-theme.css cloudflare/digiweb/web/src/styles/web-theme.test.ts cloudflare/digiweb/web/package.json cloudflare/digiweb/reference/app/globals.css
git commit -m "feat(digiweb): vendored shadcn ui set in @digithings/web + reference rewire — wave 0"
```

---

### Task 5: Proof of chain — reference route + visual verification

**Files:**
- Create: `cloudflare/digiweb/reference/app/(gallery)/ui/page.tsx`

**Interfaces:**
- Consumes: `@digithings/web/ui` (Task 4), the token bridge (Task 3), reference `@source` line (Task 4).
- Produces: the acceptance evidence for spec §5 Wave 0 — screenshots of stock components in the skin (dark + light + one livery scope).

- [ ] **Step 1: Write the proof route**

Create `cloudflare/digiweb/reference/app/(gallery)/ui/page.tsx` — a server component rendering, with no custom classes on the components themselves:
- `<Button>` in `default`, `secondary`, `outline`, `ghost` variants and `sm`/`lg` sizes, one disabled.
- `<Input placeholder="Search tickers" />` beside a plain `<label>`.
- `<Card>` with header/content/footer text.
- `<Dialog>` with trigger + content (its own `"use client"` carries interactivity).
- One section wrapped in an `.accent-digigraph` scope to prove the bridge re-resolves under a livery.

- [ ] **Step 2: Start the reference dev server and screenshot**

```bash
cd cloudflare/digiweb/reference
(nohup npm run dev -- --port 4013 > /tmp/design-reference.dev.log 2>&1 &)
```

Then with the oc-cdp harness (`/var/folders/36/1mwn8lfs7qx58560qsmy12xw0000gn/T/opencode/oc-cdp/client.mjs`):

```bash
node client.mjs go http://127.0.0.1:4013/ui
node client.mjs shot shadcn-wave0-dark.png --full
# flip theme (gallery toggle or data-theme attr), then:
node client.mjs shot shadcn-wave0-light.png --full
```

Verify against the DESIGN.md checklist, then record the verdict in the PR body: radius 0 everywhere, mono everywhere, primary button = ink fill with paper label (never accent), borders are hairlines, no shadows except the dialog overlay, input focus ring = accent color-mix.

- [ ] **Step 3: Run the full gates**

```bash
python scripts/check_frontend_canon.py
npm --workspace @digithings/web run test
npm --workspace digichat run test          # web-theme.css is shared — regression guard
cd cloudflare/digiweb/reference && npm run lint && npm run typecheck && npm run build
```

Expected: all green (digichat ≈123 files/1214 tests; canon guard clean — no new app-local css families since all new CSS is in the package sheet).

- [ ] **Step 4: Commit**

```bash
git add "cloudflare/digiweb/reference/app/(gallery)/ui/page.tsx"
git commit -m "feat(digiweb): wave 0 proof route — stock shadcn in the Instrument-Panel skin"
```

---

### Task 6: Canon docs

**Files:**
- Modify: `cloudflare/digiweb/MIGRATION.md`, `cloudflare/digiweb/ARCHITECTURE.md` (~~`cloudflare/digiweb/MANIFEST.json`~~ — struck 2026-09-16: generated file, see Step 2)

**Interfaces:**
- Consumes: Tasks 1–5 as shipped.
- Produces: the written contract Wave 1+ follows.

- [ ] **Step 1: MIGRATION.md — add the UI kit section**

Document: the vendored set lives in `@digithings/web` (`src/ui/`, Base UI base); add components by running `npx shadcn@latest add <name>` inside `cloudflare/digiweb/web` (never vendored into an app); consumers add `@source "../../web/src/ui";`; the token bridge lives in `web-theme.css`'s single `@theme inline` block (link spec §3.2); `--color-primary` is ink/paper — never accent.

- [ ] **Step 2: ARCHITECTURE.md family map**

Add the `ui` family paragraph + row to ARCHITECTURE.md's family map (source of
truth: `web/src/ui/index.ts`).

~~Add a `ui` family row to MANIFEST.json (components: button, card, dialog,
input).~~ — struck 2026-09-16: `MANIFEST.json` is generated
("do not hand-edit") by `scripts/build-manifest.mjs`, which indexes only
`reference/components` (walking past `components/ui`) and currently mis-maps
route-grouped family pages — a regen today yields 5 families vs the committed
15. A hand-added row would be dropped by the next regen. Generator fix +
package-family indexing tracked in #4225.

- [ ] **Step 3: Commit**

```bash
git add cloudflare/digiweb/MIGRATION.md cloudflare/digiweb/ARCHITECTURE.md
git commit -m "docs(digiweb): wave 0 canon — vendored ui kit contract in MIGRATION/ARCHITECTURE"
```

---

### Task 7: Ship — spec PR first, then the wave PR

**Files:** none (git/GitHub only).

**Interfaces:**
- Consumes: branch `docs/shadcn-migration-design` (spec commit `975da610e`) and the wave-0 branch.
- Produces: spec on `develop`, wave-0 PR merged referencing epic #4206.

- [ ] **Step 1: Push the wave-0 branch** (it already exists locally on this worktree with all task commits)

```bash
git push -u origin feat/shadcn-wave-0
```

- [ ] **Step 2: Push the spec branch and open its docs PR**

```bash
git push -u origin docs/shadcn-migration-design
gh pr create --base develop --head docs/shadcn-migration-design \
  --title "docs: digiweb × shadcn/ui migration design spec (#4206)" \
  --body "Spec for the digiweb shadcn migration. Refs #4206. Decisions resolved 2026-09-16 (JetBrains Mono, Base UI, single chart stack pending audit, migrate-everything)."
```

Docs-only PR: merge when CI green (no domain review required; note the hatch used in the merge comment).

- [ ] **Step 3: Open the wave-0 PR**

```bash
gh pr create --base develop --head feat/shadcn-wave-0 \
  --title "feat(digiweb): shadcn wave 0 — token bridge + vendored ui kit (#4206)" \
  --body "Wave 0 proof of chain for #4206. Spec: docs/superpowers/specs/2026-09-16-shadcn-migration-design.md. Evidence: screenshots (dark/light/livery), full gates green (web vitest, digichat regression, canon guard, reference lint/typecheck/build)."
```

- [ ] **Step 4: Review coverage, then merge when ready**

After CI is green: run the in-session fresh-context review (`/review <PR>`) per `docs/agents/CODE_REVIEW_POLICY.md`, fix findings on the branch, post the `<!-- in-session-review -->` findings comment, apply `reviewed:agent`, then merge into `develop`. Not on the human-gate list (frontend only) — agent merge is allowed once merge-ready.

---

## Self-Review

- **Spec coverage:** §3.1 (one vendored set, package components.json, `./ui` export, `@source`, reference `components/ui` partially retired — 6 dead files; the tooltip parity specimen + dot-matrix shim stay) → Tasks 2+4. §3.2 (bridge in `web-theme.css`, exact rows) → Task 3. §3.3 (preset: style lyra, Lucide, r=0, JetBrains in config) → Tasks 2+3 (app font swap deliberately Wave 1). §5 Wave 0 exit criteria (stock components in skin, preview screenshots, vitest, canon guard) → Tasks 4–5. §9 Q1/Q2 → Global Constraints + Task 2. §9 Q6 (epic referenced) → header + Task 7.
- **Placeholder scan:** no TBD/TODO; every code step carries its content; CLI-schema step is a probe (CLI-authoritative) rather than a guess, with an explicit fallback.
- **Type consistency:** `cn` path `@/lib/utils` matches what `shadcn add` writes and Task 1 provides; the `./ui` export (Task 4) and the pre-existing `./chat/dot-matrix` subpath match what the reference consumes; test file paths match the alias config.
