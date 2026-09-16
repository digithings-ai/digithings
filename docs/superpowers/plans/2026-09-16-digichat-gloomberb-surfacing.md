# digichat Gloomberb Attribution Surfacing Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Render the Gloomberb source line, free-tier delay notice, and `term.gloom.sh/?ticker=` deep link under digichat's own (vendored) tool-result pane, reusing the shipped shared helper — and render nothing when the payload carries no attribution.

**Architecture:** One additive render branch inside the vendored `ToolFallback` at `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx`: a new `ToolFallbackAttribution` presentational function reads the result envelope through `readGloomberbAttribution` from the existing `@digithings/web` workspace dependency, and renders under `ToolFallbackResult` inside `ToolFallbackContent`. The helper unwraps the digichat tool-output envelope (`{...input, result, durationMs}`), keys on the payload's `attribution` field, and validates the deep link's `term.gloom.sh` prefix. Clipped or unattributed payloads return `null` — no empty line. No stream, adapter, skin, or dependency changes.

**Tech Stack:** TypeScript/React 19, Next.js 16, assistant-ui `ToolCallMessagePartProps`, vitest 4 (happy-dom per-file pragma + `@testing-library/react`), `@digithings/web` (workspace package, barrel export of the shared helper).

**Spec:** `docs/superpowers/specs/2026-09-16-digichat-gloomberb-surfacing-design.md` — the plan argues from the spec; executors read both.

**Issue:** [#4098](https://github.com/digithings-ai/digithings/issues/4098) (digichat half; dashboard half shipped in #4193/#4204).

## Global Constraints

- **Reuse the shipped copy constants — no new strings.** The line renders the payload's `attribution` / `delay_notice` fields (built from `digiquant/src/digiquant/data/gloomberb/attribution.py:21-23`); the href is the payload's `source_url` (built at `attribution.py:26-28`). The only literal is the shipped anchor label `Open in Gloomberb` (identical to #4130, `cloudflare/digiweb/web/src/components/chat/gallery-thread/tool-fallback.aui.tsx:343`). No i18n, no paraphrase.
- **External links only — no iframes.** `target="_blank" rel="noopener noreferrer"`. Iframing `term.gloom.sh` is ruled out (`X-Frame-Options: DENY` + `frame-ancestors 'none'`; `docs/superpowers/specs/2026-09-12-digifetch-scoping-design.md` §7-§8).
- **No ticker extraction.** digichat never constructs a ticker URL from tool args or result rows; the link exists only when the payload carries `source_url` (single listing addressed). No `source_url` → attribution without a link. No `attribution` → nothing.
- **Lowercase digi\* naming** in commits, docs, and prose (`digichat`, `digithings`, `digiquant`).
- **No new dependencies, no new network calls.** `@digithings/web` is already a digichat dependency (`cloudflare/digichat/package.json`); the helper is pure string/object logic; anchors are user-initiated navigation. This is **not** on the human-gate list (`AGENTS.md` § Human gate) — no agent-merge block.
- **Branch/issue discipline.** `task/4098-*` cut by `make task ISSUE=4098` from `refs/remotes/origin/module/digiquant` (the PR base is `module/digiquant`; `scripts/project_routing.json` maps `component:digiquant`). PR references #4098; every commit traces to it.
- **Tests.** vitest from the worktree root; component tests carry `// @vitest-environment happy-dom`. Run `npm run test --workspace digichat`. Do not weaken or skip existing assertions.
- **Test counts may drift** with unrelated `develop` commits; the gate is exit 0, not a pinned number (2026-09-16 baseline: 125 test files).
- **Cross-references:** #4130 (shipped gallery-thread attribution line — the design being mirrored), #4131 (digigraph clipping — a named dependency, **not fixed here**; the UI must degrade cleanly), #4193/#4204 (shipped dashboard precedent), #4110 (digifetch epic), #4069 (Gloomberb client).

**Files touched overall:**
- Modify: `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx`, `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.test.tsx`
- Create: `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.source.test.ts`
- Docs: `cloudflare/digichat/src/app/(baseline)/stock/SOURCE.md`, `cloudflare/digichat/ARCHITECTURE.md`
- No changes to `@digithings/web`, the first-party gallery thread, stream parts, the adapters, or any skin file.

---

### Task 1: Task branch + shared-helper availability

**Files:**
- No repo files change in this task; it creates the worktree/branch every later task commits on.

**Interfaces:**
- Consumes: issue #4098 labels; `scripts/project_routing.json`.
- Produces: a `task/4098-*` worktree based on `refs/remotes/origin/module/digiquant`; verified import seam `readGloomberbAttribution` from `@digithings/web`.

- [ ] **Step 1: Cut the task branch and worktree**

From a current checkout (repo root), run:

```bash
git fetch origin
make task ISSUE=4098
```

Expected: a worktree under `.worktrees/` on branch `task/4098-<slug>`, cut from
`refs/remotes/origin/module/digiquant`.

If `make task` refuses with "module/digiquant is N commits behind origin/develop",
sync the module branch first (module branches are ruleset-protected — no
force-push; a normal PR is the sync path):

```bash
gh pr create --base module/digiquant --head develop \
  --title "chore(digiquant): sync module branch with develop" \
  --body "Unblock the #4098 task work; tree-only sync, no content change."
# merge once CI is green, then re-run make task ISSUE=4098
```

All later commands run from the **task worktree root**.

- [ ] **Step 2: Verify the dependency and the export seam**

```bash
rg -n '"@digithings/web"' cloudflare/digichat/package.json
```
Expected: `    "@digithings/web": "*",` (digichat already depends on the package).

```bash
rg -n "readGloomberbAttribution|GLOOMBERB_ATTRIBUTION|gloomberbTickerUrl" cloudflare/digiweb/web/src/index.ts
```
Expected: hits inside the barrel block at lines 482-489 — the helper, its
constants, and `gloomberbTickerUrl` are importable from `@digithings/web`. There
is no `./lib/gloomberb` subpath in the package `exports` map, so the barrel is
the import path.

```bash
rg -n '^import .*\.css' cloudflare/digiweb/web/src/index.ts
```
Expected: **no output** — the barrel is CSS-free, so importing it from a
component cannot leak styles into the isolated `/baseline` preview.

```bash
rg -n 'from "@digithings/web"' cloudflare/digichat/src --glob '!*.test.*' | head -5
```
Expected: existing consumers (e.g. `src/components/ui/button.tsx`) — the import
pattern is established in this app.

- [ ] **Step 3: Install workspaces**

```bash
npm ci
```
Expected: exit 0; `cloudflare/digichat` and `cloudflare/digiweb/web` resolved
from the root lockfile.

- [ ] **Step 4: No commit**

This task produces no file changes; the first commit is Task 2's.

---

### Task 2: `ToolFallbackAttribution` component + unit tests

**Files:**
- Modify: `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx` (import after line 29; new function after `ToolFallbackResult`, which ends at line 316; export list at lines 792-801)
- Test: `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.test.tsx` (import at line 10; append a describe block at end of file)

**Interfaces:**
- Consumes: `readGloomberbAttribution(result: unknown): GloomberbAttribution | null` from `@digithings/web` (`cloudflare/digiweb/web/src/lib/gloomberb.ts:50-73`). It unwraps the `result` key of the tool-output envelope and JSON-string results, requires a non-blank `attribution` string, and returns `{ attribution, delayNotice?, sourceUrl? }` with `sourceUrl` only for `term.gloom.sh` links.
- Produces: `ToolFallbackAttribution` — props `React.ComponentProps<"div"> & { result?: unknown }`; renders a `[data-slot="tool-fallback-attribution"]` row or `null`. Consumed by Task 3's wiring and by the unit tests below.

- [ ] **Step 1: Write the failing tests**

In `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.test.tsx`,
change line 10 to import the new component:

```tsx
import { ToolFallback, ToolFallbackAttribution, formatToolDuration } from "./tool-fallback.aui";
```

Append this block at the end of the file:

```tsx
describe("stock ToolFallbackAttribution", () => {
  it("renders the source line, delay notice, and terminal deep link", () => {
    render(
      <ToolFallbackAttribution
        result={{
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=AAPL",
          },
          durationMs: 12,
        }}
      />,
    );
    expect(screen.getByText("Sourced from Gloomberb")).toBeTruthy();
    expect(screen.getByText(/Data delayed up to 15 minutes/)).toBeTruthy();
    const link = screen.getByRole("link", { name: /Open in Gloomberb/ });
    expect(link.getAttribute("href")).toBe("https://term.gloom.sh/?ticker=AAPL");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("renders the source line without a link when no single listing was addressed", () => {
    render(
      <ToolFallbackAttribution
        result={{
          result: {
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
          },
        }}
      />,
    );
    expect(screen.getByText("Sourced from Gloomberb")).toBeTruthy();
    expect(screen.queryByRole("link")).toBeNull();
  });

  it("renders nothing for an unattributed tool result", () => {
    const { container } = render(
      <ToolFallbackAttribution
        result={{ result: { rows: [{ symbol: "AAPL" }] }, durationMs: 4 }}
      />,
    );
    expect(
      container.querySelector('[data-slot="tool-fallback-attribution"]'),
    ).toBeNull();
  });

  it("renders nothing for a digigraph-clipped payload (#4131)", () => {
    const { container } = render(
      <ToolFallbackAttribution
        result={{
          result: {
            truncated: true,
            preview: '{"data":{"attribution":"Sourced fr… [truncated]',
          },
        }}
      />,
    );
    expect(
      container.querySelector('[data-slot="tool-fallback-attribution"]'),
    ).toBeNull();
  });

  it("reads a JSON-string result envelope", () => {
    render(
      <ToolFallbackAttribution
        result={{
          result: JSON.stringify({
            attribution: "Sourced from Gloomberb",
            delay_notice: "Data delayed up to 15 minutes",
            source_url: "https://term.gloom.sh/?ticker=BTC-USD",
          }),
        }}
      />,
    );
    const link = screen.getByRole("link", { name: /Open in Gloomberb/ });
    expect(link.getAttribute("href")).toBe(
      "https://term.gloom.sh/?ticker=BTC-USD",
    );
  });
});
```

- [ ] **Step 2: Run the tests to verify they fail**

Run (from the task worktree root):
```bash
npm run test --workspace digichat -- "src/app/(baseline)/stock/tool-fallback.aui.test.tsx"
```
Expected: FAIL — the module does not export `ToolFallbackAttribution`
(Vite/esbuild: `does not provide an export named 'ToolFallbackAttribution'`),
and the five new cases cannot run. The five existing tests still pass.

- [ ] **Step 3: Add the import**

In `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx`, append
after the last import (line 29, `import { Textarea } from "./ui/textarea";`):

```tsx
import { readGloomberbAttribution } from "@digithings/web";
```

- [ ] **Step 4: Add the component**

Insert after `ToolFallbackResult` (ends at line 316) and before
`function ToolFallbackError(` (line 318):

```tsx
function ToolFallbackAttribution({
  result,
  className,
  ...props
}: React.ComponentProps<"div"> & {
  result?: unknown;
}) {
  const attribution = readGloomberbAttribution(result);
  if (!attribution) return null;

  return (
    <div
      data-slot="tool-fallback-attribution"
      className={cn(
        "aui-tool-fallback-attribution text-muted-foreground flex flex-wrap items-baseline gap-x-2 gap-y-1 text-xs",
        className,
      )}
      {...props}
    >
      <span>{attribution.attribution}</span>
      {attribution.delayNotice ? <span>· {attribution.delayNotice}</span> : null}
      {attribution.sourceUrl ? (
        <a
          href={attribution.sourceUrl}
          target="_blank"
          rel="noopener noreferrer"
          className="aui-tool-fallback-attribution-link text-foreground/90 underline-offset-2 hover:underline"
        >
          Open in Gloomberb
        </a>
      ) : null}
    </div>
  );
}
```

- [ ] **Step 5: Export the component**

In the `export { ... }` block at the end of the file (lines 792-801), add
`ToolFallbackAttribution,` after `ToolFallbackApproval,`:

```tsx
export {
  ToolFallback,
  ToolFallbackRoot,
  ToolFallbackTrigger,
  ToolFallbackContent,
  ToolFallbackArgs,
  ToolFallbackResult,
  ToolFallbackError,
  ToolFallbackApproval,
  ToolFallbackAttribution,
};
```

(Do **not** add it to the `ToolFallback` composite object at lines 771-789 —
the shipped #4130 gallery line is not on its composite either.)

- [ ] **Step 6: Run the tests to verify they pass**

Run: `npm run test --workspace digichat -- "src/app/(baseline)/stock/tool-fallback.aui.test.tsx"`
Expected: PASS — 10 tests (5 existing + 5 new).

- [ ] **Step 7: Commit**

```bash
git add cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx \
        cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.test.tsx
git commit -m "feat(digichat): Gloomberb attribution line for tool results (#4098)"
```

---

### Task 3: Wire the line into `ToolFallback` + integration tests + source guard

**Files:**
- Modify: `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx` (`ToolFallbackImpl` result branch, lines 763-765)
- Modify: `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.test.tsx` (testing-library import at line 3; append a wiring describe block)
- Test: `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.source.test.ts` (new; source guard)

**Interfaces:**
- Consumes: `ToolFallbackAttribution` (Task 2); the tool part's `result` prop shape written by `cloudflare/digichat/src/lib/ui-stream-parts.ts:200-223` (`{...input, result, durationMs}`).
- Produces: expanded tool rows in the `base`/`chatgpt` skins and the `/baseline` preview render the attribution footer; collapsed rows and unattributed/clipped payloads are unchanged.

- [ ] **Step 1: Write the failing wiring tests**

In `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.test.tsx`,
add `fireEvent` to the testing-library import (line 3):

```tsx
import { fireEvent, render, screen } from "@testing-library/react";
```

Append this block at the end of the file:

```tsx
describe("stock ToolFallback attribution wiring", () => {
  function renderCompleted(result: unknown, toolName = "digifetch_quote") {
    return render(
      <ToolFallback
        type="tool-call"
        toolCallId="t-g1"
        toolName={toolName}
        args={{ symbol: "AAPL" }}
        argsText='{"symbol":"AAPL"}'
        result={result}
        status={{ type: "complete" }}
        addResult={() => undefined}
        resume={() => undefined}
        respondToApproval={async () => undefined}
      />,
    );
  }

  it("credits Gloomberb under the expanded Result pane", () => {
    renderCompleted({
      result: {
        attribution: "Sourced from Gloomberb",
        delay_notice: "Data delayed up to 15 minutes",
        source_url: "https://term.gloom.sh/?ticker=AAPL",
      },
      durationMs: 12,
    });
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Sourced from Gloomberb")).toBeTruthy();
    const link = screen.getByRole("link", { name: /Open in Gloomberb/ });
    expect(link.getAttribute("href")).toBe("https://term.gloom.sh/?ticker=AAPL");
    expect(link.getAttribute("target")).toBe("_blank");
    expect(link.getAttribute("rel")).toBe("noopener noreferrer");
  });

  it("keeps the expanded Result pane unchanged for a clipped payload", () => {
    renderCompleted({
      result: { truncated: true, preview: '{"data":{' },
      durationMs: 12,
    });
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Result:")).toBeTruthy();
    expect(screen.queryByText("Sourced from Gloomberb")).toBeNull();
  });

  it("keeps the expanded Result pane unchanged for an unattributed payload", () => {
    renderCompleted(
      { result: { rows: [{ symbol: "AAPL" }] }, durationMs: 12 },
      "digifetch_earnings_calendar",
    );
    fireEvent.click(screen.getByRole("button"));
    expect(screen.getByText("Result:")).toBeTruthy();
    expect(screen.queryByText("Sourced from Gloomberb")).toBeNull();
  });
});
```

Note: the trigger is a Base UI `CollapsibleTrigger` (the row's only button).
If `fireEvent.click` does not toggle under happy-dom, use
`await userEvent.click(screen.getByRole("button"))` (`@testing-library/user-event`
is already a devDependency of this app) — the assertions do not change.

- [ ] **Step 2: Write the source guard test**

Create `cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.source.test.ts`:

```ts
import { readFileSync } from "node:fs";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";
import { describe, expect, it } from "vitest";

const here = dirname(fileURLToPath(import.meta.url));
const source = readFileSync(join(here, "tool-fallback.aui.tsx"), "utf8");

describe("stock ToolFallback source guard", () => {
  it("reads attribution through the shared @digithings/web helper", () => {
    expect(source).toMatch(
      /import\s*\{\s*readGloomberbAttribution\s*\}\s*from\s*["']@digithings\/web["']/,
    );
  });

  it("never hardcodes the canonical strings or the terminal URL", () => {
    expect(source).not.toContain("Sourced from Gloomberb");
    expect(source).not.toContain("Data delayed up to 15 minutes");
    expect(source).not.toContain("https://term.gloom.sh");
  });
});
```

- [ ] **Step 3: Run the tests to verify the wiring fails**

Run:
```bash
npm run test --workspace digichat -- "src/app/(baseline)/stock/tool-fallback.aui.test.tsx"
```
Expected: FAIL — the first new case fails with `Unable to find an element with
the text: Sourced from Gloomberb` (the line is implemented but not wired into
`ToolFallbackImpl`); the clipped/unattributed cases pass; the 10 earlier tests
pass.

Run:
```bash
npm run test --workspace digichat -- "src/app/(baseline)/stock/tool-fallback.source.test.ts"
```
Expected: PASS — Task 2 already added the import and no hardcoded strings (this
file is a pin, not a red test).

- [ ] **Step 4: Wire the line into `ToolFallbackImpl`**

Replace lines 763-765:

```tsx
        {!isCancelled && !isErrorStatus && (
          <ToolFallbackResult result={result} />
        )}
```

with:

```tsx
        {!isCancelled && !isErrorStatus && (
          <>
            <ToolFallbackResult result={result} />
            <ToolFallbackAttribution result={result} />
          </>
        )}
```

- [ ] **Step 5: Run the tests to verify they pass**

Run:
```bash
npm run test --workspace digichat -- "src/app/(baseline)/stock/tool-fallback.aui.test.tsx" "src/app/(baseline)/stock/tool-fallback.source.test.ts"
```
Expected: PASS — 13 tests in the component file (10 + 3 wiring) and 2 in the
source guard.

- [ ] **Step 6: Commit**

```bash
git add cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.tsx \
        cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.aui.test.tsx \
        cloudflare/digichat/src/app/(baseline)/stock/tool-fallback.source.test.ts
git commit -m "feat(digichat): wire Gloomberb attribution into the stock tool fallback (#4098)"
```

---

### Task 4: Docs + manual dev verification

**Files:**
- Modify: `cloudflare/digichat/src/app/(baseline)/stock/SOURCE.md`
- Modify: `cloudflare/digichat/ARCHITECTURE.md:1327` (the §9 digigraph paragraph)

**Interfaces:**
- Consumes: Tasks 2-3 as shipped on the branch.
- Produces: the vendored-file amendment on the record; interface/behaviour doc updated per `AGENTS.md` ("Update `{component}/ARCHITECTURE.md` after any interface or behavior change"); manual evidence for the PR body.

- [ ] **Step 1: Amend the vendored-file rules**

In `cloudflare/digichat/src/app/(baseline)/stock/SOURCE.md`, extend the "The
only edits here are:" list (after the `dialog.tsx` bullet) with:

```md
- `tool-fallback.aui.tsx` adds the Gloomberb attribution footer
  (`ToolFallbackAttribution`, reading `readGloomberbAttribution` from
  `@digithings/web`) under the Result pane — the same line the first-party
  gallery thread renders (#4098). No other styling changes.
```

Leave the closing sentence ("Do not restyle these files for digichat. `/baseline`
mounts this Thread with no extra chrome.") unchanged.

- [ ] **Step 2: Update the digichat architecture note**

In `cloudflare/digichat/ARCHITECTURE.md`, in the §9 digigraph (primary)
paragraph (line 1327), find the sentence:

```
unattributed payloads (and off-terminal `source_url` values) render nothing extra.
```

Insert immediately after it:

```
The digichat-vendored stock fallback (`(baseline)/stock/tool-fallback.aui.tsx`,
used by the `base`/`chatgpt` skins and the `/baseline` preview) renders the same
line through the same helper (#4098).
```

- [ ] **Step 3: Run the static gates**

From the task worktree root:

```bash
npm run test --workspace digichat
npm run lint --workspace digichat
python3 scripts/check_frontend_canon.py
(cd cloudflare/digichat && npx tsc --noEmit)
```

Expected: digichat suite green (2026-09-16 baseline 125 files; 126 after the
new guard file — counts drift with `develop`, exit 0 is the gate); lint 0
errors (pre-existing warnings allowed); canon guard clean (no CSS added);
`tsc` exit 0.

- [ ] **Step 4: Manual dev verification**

```bash
make digichat-dev
```

Then, in a browser:

1. Open `http://127.0.0.1:3000/baseline?skin=base` and
   `http://127.0.0.1:3000/baseline?skin=chatgpt`, and the product route `/`
   (`base` is the non-first-party default skin).
2. Send a message that makes the model call a Gloomberb tool
   (e.g. "Get the latest quote for AAPL with digifetch_quote"). If the stack
   (`make stack-local`) and outbound access to `api.gloom.sh` are available and
   `GLOOMBERB_ENABLED` is on, expand the tool row and confirm:
   `Sourced from Gloomberb · Data delayed up to 15 minutes · Open in Gloomberb`,
   with the anchor opening `https://term.gloom.sh/?ticker=AAPL` in a new tab.
3. Send a message that calls an unattributed tool (e.g. `digisearch` or the
   Yahoo-backed `digifetch_earnings_calendar`), expand the row, and confirm the
   Result pane is unchanged — no empty attribution line, no `Sourced from
   Gloomberb` text.
4. Confirm no console errors and that collapsed rows look unchanged.

If the live backend/egress is unavailable in this environment, say so in the PR
body: the vitest acceptance (Task 3) stands as the behavioural proof; do not
fabricate screenshots.

- [ ] **Step 5: Commit**

```bash
git add cloudflare/digichat/src/app/(baseline)/stock/SOURCE.md cloudflare/digichat/ARCHITECTURE.md
git commit -m "docs(digichat): record the Gloomberb attribution line in SOURCE/ARCHITECTURE (#4098)"
```

---

### Task 5: Ship — PR, review coverage, merge

**Files:**
- No file changes; git/GitHub only.

**Interfaces:**
- Consumes: the four commits from Tasks 2-4.
- Produces: merged PR into `module/digiquant` referencing #4098.

- [ ] **Step 1: Push and open the PR**

```bash
git push -u origin HEAD
gh pr create --base module/digiquant --head "$(git branch --show-current)" \
  --title "feat(digichat): surface Gloomberb attribution + deep link in tool results (#4098)" \
  --body "$(cat <<'EOF'
Fixes #4098 (digichat half; the dashboard half shipped in #4193/#4204).

Adds the Gloomberb source line, delay notice, and `term.gloom.sh/?ticker=`
deep link under digichat's vendored tool-result pane
(`(baseline)/stock/tool-fallback.aui.tsx`, used by the `base`/`chatgpt` skins
and the `/baseline` preview), reusing `readGloomberbAttribution` from
`@digithings/web`. The first-party `digichat` skin already renders this line
via #4130; this closes the remaining digichat-owned surface.

- No new strings: payload `attribution`/`delay_notice`/`source_url` plus the
  shipped `Open in Gloomberb` label.
- No new dependency, no network call, no iframe (external anchor,
  `target="_blank" rel="noopener noreferrer"`).
- Degrades cleanly: unattributed or clipped payloads render nothing.
- Known dependency: payloads >12k chars lose the attribution upstream
  (#4131, digigraph clipper) — the UI needs no change when that lands.

Spec: docs/superpowers/specs/2026-09-16-digichat-gloomberb-surfacing-design.md
Plan: docs/superpowers/plans/2026-09-16-digichat-gloomberb-surfacing.md
EOF
)"
```

- [ ] **Step 2: Review coverage**

Wait for CI, then run the in-session fresh-context review required by
`docs/agents/CODE_REVIEW_POLICY.md` (`/review <PR>` or an equivalent
fresh-context pass). Fix findings on the same branch, post the surviving
findings as a PR comment starting with `<!-- in-session-review -->`, and apply
the `reviewed:agent` label. Do not merge with unresolved review threads.

- [ ] **Step 3: Merge when ready**

```bash
gh pr view <N> --json mergeable,reviewDecision,statusCheckRollup
git log --merges origin/module/digiquant -5 --oneline   # mirror this base's landing style
gh pr merge <N> --merge   # or --squash if the log above shows squash lands
```

Merge-ready means required CI green, `mergeable` `CLEAN`, review findings
triaged, and review coverage on the record. This change is **not** on the human
gate (no `digikey/`, no brokers/live-trading, no new dependency or network
exposure) — agent merge applies. If `gh` returns 403, report that; do not
pretend it merged.

- [ ] **Step 4: Leave #4131 open**

Do not close or fold in #4131 (digigraph clipping) — it is a separate fix for
large payloads and was never in #4098's UI scope. `Fixes #4098` in the PR body
closes the surfacing issue on merge.

---

## Self-Review

**1. Spec coverage:** §1 goal (digichat's vendored fallback; helper reuse; SOURCE.md amendment) → Tasks 1-4. §2.1-2.4 anchors → consumed by the plan's code and interfaces. §2.5 clipping dependency → Task 3's clipped test + Task 5 Step 4. §3 chosen location (footer line, rejected source-part/activity-line options) → Task 2/3 implementation. §4 contracts: presence → Task 2 tests; deep link from `source_url` (no ticker extraction) → Task 2 test "source line without a link" + 5 tests in the no-URL case; copy → source guard (Task 3) + payload-driven render; external links → anchor attrs asserted in Tasks 2/3; dependency contract → Task 1 Steps 2-3; vendoring contract → Task 4 Step 1. §5 normative values → the exact strings/attrs in Tasks 2-3 and the tests. §6 sequencing → the five tasks, in order. §7 verification → Task 3 Step 5, Task 4 Steps 3-4, full-suite command in Task 4. §8 risks → mitigations carried by the source guard, the degradation tests, and the #4131 note. §9 out of scope → respected (no gallery/web/stream/adapter/skin edits in any task). §10 open questions → Q1 recorded in Task 1 Step 2 (barrel is the only entry today); Q2/Q3 need no code in this plan.

**2. Placeholder scan:** no TBD/TODO/"similar to"; every code step carries its
full content; every command has an expected result. The only conditional in the
plan is the Base UI click fallback in Task 3 Step 1 (explicit alternative, not
a placeholder) and the module-branch sync recipe in Task 1 (a documented repo
procedure).

**3. Type consistency:** `ToolFallbackAttribution` — exported from
`(baseline)/stock/tool-fallback.aui.tsx`, props
`React.ComponentProps<"div"> & { result?: unknown }`, returns `JSX.Element | null`;
`readGloomberbAttribution(result)` returns
`{ attribution: string; delayNotice?: string; sourceUrl?: string } | null`
(imported once, never re-typed); test props match the existing
`ToolCallMessagePartProps` usage in the same file (`type`, `toolCallId`,
`toolName`, `args`, `argsText`, `result`, `status`, `addResult`, `resume`,
`respondToApproval`); `data-slot` / anchor attributes identical to #4130
(`gallery-thread/tool-fallback.aui.tsx:315-348`).
