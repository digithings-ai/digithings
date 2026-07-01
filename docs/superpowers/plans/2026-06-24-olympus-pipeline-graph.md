# Olympus Pipeline Graph (Surface 1) Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Replace the `/pipeline` placeholder with a per-day, zoomable/pannable graph of the daily decision pipeline (Inputs → Research → Synthesis → Selection → Decision), where every leaf node opens its persisted output via the existing document-reader stack.

**Architecture:** A pure layout core (static topology + runtime fan-out widths → laid-out node coordinates) drives a single zoomable SVG/DOM canvas with selective in-place expansion. Node-detail reuses the `library/*` views via `use-library-document`, keyed on `document_key`. Deep-linking uses the already-landed grammar in `lib/pipeline-links.ts`.

**Tech Stack:** Next.js 16 (`output:'export'`, `basePath:'/olympus'`), React 19, Tailwind v4, lucide-react, vitest (node env, `renderToStaticMarkup` — no jsdom), `@supabase/supabase-js`.

## Global Constraints

- Polars/pandas N/A (frontend). Strict TypeScript; no `any` in new code.
- **F5 token rule:** cyan `--accent` (`bg-fin-blue`/`text-fin-blue` ≡ accent) for chrome/links/conviction/fresh-dot only; `fin-green`/`fin-red` strictly for signed financial values; `fin-amber` for caution/stale. No gradients beyond the regime wash. No `text-fin-purple`, no `#a78bfa`, no raw `rgba(59,130,246)` literals (enforced by `lib/token-hygiene.test.ts`).
- Tests run in node env via `renderToStaticMarkup` — **no jsdom, no DOM events**. Interactive behavior (pan/zoom/camera) is NOT unit-tested; it is verified by `npx next build` + manual/visual against the mockup. Pure logic (topology, layout coordinates, deep-link parse, node→key mapping, fan-out counts) IS unit-tested.
- Every node-detail render path reuses the existing stack — **do not re-implement document views**: `DocumentExpandInline`, `LibraryDocumentBody`, `DigestDocumentView`, `DeliberationDocumentView`, `AnalystDocumentView`, `RebalanceDocumentView`, `OpportunityScreenerDocumentView`, `GenericDiffDocumentView`, fed by `lib/hooks/use-library-document.ts`.
- Reference mockup (read it before building the canvas): `/Users/chrisstefan/.claude/jobs/ff9c1ed3/tmp/pipeline-mockup.html` (v3-hybrid-seq-par). Known gaps to close: camera auto-center on expand; zero overflow + production-clean SVG connectors.
- Deep-link grammar (LOCKED, already in `lib/pipeline-links.ts`): `/pipeline?date=YYYY-MM-DD&stage=<stage>&node=<document_key>`. `PipelineStage = 'inputs'|'research'|'synthesis'|'selection'|'decision'`.
- Exit gate (every task): `npx vitest run` green · `npx tsc --noEmit` introduces no new errors (baseline: 4 pre-existing in `DecisionQuality.test.tsx` + `security-headers.test.ts`) · token-hygiene test passes · conventional commit `Refs #1048`.

---

## File Structure

| File | Responsibility |
|---|---|
| `lib/pipeline-topology.ts` (new) | Static pipeline topology: stages, sequential sub-steps, parallel fan-out descriptors. Pure data + helpers. |
| `lib/pipeline-topology.test.ts` (new) | Topology invariants. |
| `lib/pipeline-graph-data.ts` (new) | Map a day's `documents` rows → runtime fan-out counts + which leaf nodes have output. Pure transform over fetched rows. |
| `lib/pipeline-graph-data.test.ts` (new) | Fan-out counting + presence. |
| `lib/pipeline-layout.ts` (new) | Pure layout engine: (topology + expansion state) → positioned nodes + connector segments. Horizontal=sequential, vertical=parallel. |
| `lib/pipeline-layout.test.ts` (new) | Coordinate/ordering/no-overlap assertions. |
| `lib/pipeline-links.ts` (extend) | Add `nodeDocumentKey(stage, subStep, branchIndex?)` resolver + `parsePipelineParams`. |
| `lib/pipeline-links.test.ts` (extend) | Resolver + parse round-trip. |
| `components/pipeline/PipelineCanvas.tsx` (new) | The zoomable/pannable canvas: renders positioned nodes + SVG connectors; owns expansion + camera state. |
| `components/pipeline/PipelineNode.tsx` (new) | Single node (stage / sub-step / fan-out / leaf) with count badge + expand affordance. |
| `components/pipeline/PipelineConnectors.tsx` (new) | SVG connector layer (clean curves/orthogonals). |
| `components/pipeline/useCanvasCamera.ts` (new) | Pan/zoom/fit/auto-center controller hook. |
| `components/pipeline/PipelineNodeDetail.tsx` (new) | Node-detail container: desktop side panel / mobile bottom sheet, wrapping the reused library views. |
| `components/pipeline/PipelineSummaryStrip.tsx` (new) | Top strip: digest headline + regime chips + the decision (absorbs "The Read"). |
| `components/pipeline/PipelineDaySelector.tsx` (new) | Day selector scoping the graph to a date. |
| `components/pipeline/PipelineClient.tsx` (new) | Client shell: data load, deep-link hydration, layout state, composition. |
| `app/pipeline/page.tsx` (replace) | Mount `PipelineClient` (remove the `/why` redirect). |
| `app/pipeline/page.test.ts` (new) | Static-render smoke + deep-link param wiring. |

Phase A (Tasks 1–4) is parallelizable — four mostly-independent pure modules. Phase B (5–10) is sequential (canvas depends on layout). Phase C (11) integrates.

---

## Phase A — Pure model & layout core

### Task 1: Pipeline topology model

**Files:**
- Create: `frontend/olympus/lib/pipeline-topology.ts`
- Test: `frontend/olympus/lib/pipeline-topology.test.ts`

**Interfaces:**
- Produces:
  ```ts
  export type PipelineStageId = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';
  export interface FanoutDescriptor { id: string; label: string; defaultCount: number; }
  export interface SubStep { id: string; label: string; fanout?: FanoutDescriptor; }
  export interface StageDef { id: PipelineStageId; label: string; subSteps: SubStep[]; }
  export const PIPELINE_TOPOLOGY: StageDef[];
  export function stageById(id: PipelineStageId): StageDef | undefined;
  ```

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { PIPELINE_TOPOLOGY, stageById } from './pipeline-topology';

describe('pipeline topology', () => {
  it('has the five stages in pipeline order', () => {
    expect(PIPELINE_TOPOLOGY.map((s) => s.id)).toEqual([
      'inputs', 'research', 'synthesis', 'selection', 'decision',
    ]);
  });
  it('research carries the documented fan-outs', () => {
    const research = stageById('research')!;
    const fanouts = Object.fromEntries(
      research.subSteps.filter((s) => s.fanout).map((s) => [s.id, s.fanout!.defaultCount]),
    );
    expect(fanouts).toMatchObject({ 'alt-data': 6, sectors: 12 });
  });
  it('selection has analysts and deliberation fan-outs and a commit-free spine', () => {
    const sel = stageById('selection')!;
    expect(sel.subSteps.map((s) => s.id)).toEqual([
      'thesis', 'screener', 'analysts', 'deliberation', 'pm-direction', 'risk-sizing',
    ]);
    expect(sel.subSteps.find((s) => s.id === 'analysts')!.fanout).toBeTruthy();
  });
});
```

- [ ] **Step 2: Run test to verify it fails** — `npx vitest run lib/pipeline-topology.test.ts` → FAIL (module not found).

- [ ] **Step 3: Implement** `pipeline-topology.ts` encoding the spec's mapping table:

```ts
export type PipelineStageId = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';

export interface FanoutDescriptor { id: string; label: string; defaultCount: number; }
export interface SubStep { id: string; label: string; fanout?: FanoutDescriptor; }
export interface StageDef { id: PipelineStageId; label: string; subSteps: SubStep[]; }

export const PIPELINE_TOPOLOGY: StageDef[] = [
  { id: 'inputs', label: 'Inputs', subSteps: [
    { id: 'preflight', label: 'Preflight / market data' },
  ]},
  { id: 'research', label: 'Research', subSteps: [
    { id: 'alt-data', label: 'Alt-data', fanout: { id: 'alt-data', label: 'Alt-data', defaultCount: 6 } },
    { id: 'institutional', label: 'Institutional', fanout: { id: 'institutional', label: 'Institutional', defaultCount: 2 } },
    { id: 'macro', label: 'Macro' },
    { id: 'asset-classes', label: 'Asset-classes', fanout: { id: 'asset-classes', label: 'Asset-classes', defaultCount: 6 } },
    { id: 'sectors', label: 'Sectors', fanout: { id: 'sectors', label: 'Sectors', defaultCount: 12 } },
  ]},
  { id: 'synthesis', label: 'Synthesis', subSteps: [
    { id: 'consolidate', label: 'Consolidate bias' },
    { id: 'digest', label: 'Daily digest' },
  ]},
  { id: 'selection', label: 'Selection', subSteps: [
    { id: 'thesis', label: 'Thesis framing' },
    { id: 'screener', label: 'Screener' },
    { id: 'analysts', label: 'Analysts', fanout: { id: 'analysts', label: 'Analysts', defaultCount: 0 } },
    { id: 'deliberation', label: 'Deliberation', fanout: { id: 'deliberation', label: 'Deliberation', defaultCount: 0 } },
    { id: 'pm-direction', label: 'PM direction' },
    { id: 'risk-sizing', label: 'Risk sizing' },
  ]},
  { id: 'decision', label: 'Decision', subSteps: [
    { id: 'commit', label: 'Commit' },
  ]},
];

export function stageById(id: PipelineStageId): StageDef | undefined {
  return PIPELINE_TOPOLOGY.find((s) => s.id === id);
}
```

- [ ] **Step 4: Run test to verify it passes** — `npx vitest run lib/pipeline-topology.test.ts` → PASS.

- [ ] **Step 5: Commit** — `git add frontend/olympus/lib/pipeline-topology.* && git commit -m "feat(olympus): pipeline topology model (Surface 1, Task 1)\n\nRefs #1048"`

---

### Task 2: Runtime fan-out widths + node presence from documents

**Files:**
- Create: `frontend/olympus/lib/pipeline-graph-data.ts`
- Test: `frontend/olympus/lib/pipeline-graph-data.test.ts`

**Interfaces:**
- Consumes: `documents` rows for a day — `{ document_key: string }[]` (the existing shape from `lib/queries.ts`; verify field name with `grep "document_key" lib/queries.ts`).
- Produces:
  ```ts
  export interface PipelineDayData { fanoutCounts: Record<string, number>; presentKeys: Set<string>; }
  export function buildPipelineDayData(docs: { document_key: string }[]): PipelineDayData;
  ```
  Counts: `alt-data` = docs with key prefix `alt-`; `institutional` = `inst-`; `sectors` = `sector-` (excluding `sector-scorecard`); `analysts` = `analyst/`; `deliberation` = `deliberation/`. `presentKeys` = the raw set, for leaf enable/disable.

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { buildPipelineDayData } from './pipeline-graph-data';

describe('buildPipelineDayData', () => {
  it('counts fan-outs by document_key prefix', () => {
    const docs = [
      { document_key: 'alt-credit' }, { document_key: 'alt-flows' },
      { document_key: 'sector-tech' }, { document_key: 'sector-scorecard' },
      { document_key: 'analyst/SPY' }, { document_key: 'deliberation/SPY' },
      { document_key: 'digest' },
    ];
    const d = buildPipelineDayData(docs);
    expect(d.fanoutCounts['alt-data']).toBe(2);
    expect(d.fanoutCounts['sectors']).toBe(1); // scorecard excluded
    expect(d.fanoutCounts['analysts']).toBe(1);
    expect(d.presentKeys.has('digest')).toBe(true);
  });
});
```

- [ ] **Step 2: Run test → FAIL.**

- [ ] **Step 3: Implement** the prefix-counting transform (pure; no I/O).

```ts
import type { PipelineDayData } from './pipeline-topology'; // if needed; else inline the interface here

const PREFIX_COUNTERS: { fanoutId: string; match: (k: string) => boolean }[] = [
  { fanoutId: 'alt-data', match: (k) => k.startsWith('alt-') },
  { fanoutId: 'institutional', match: (k) => k.startsWith('inst-') },
  { fanoutId: 'sectors', match: (k) => k.startsWith('sector-') && k !== 'sector-scorecard' },
  { fanoutId: 'analysts', match: (k) => k.startsWith('analyst/') },
  { fanoutId: 'deliberation', match: (k) => k.startsWith('deliberation/') },
];

export interface PipelineDayData { fanoutCounts: Record<string, number>; presentKeys: Set<string>; }

export function buildPipelineDayData(docs: { document_key: string }[]): PipelineDayData {
  const fanoutCounts: Record<string, number> = {};
  const presentKeys = new Set<string>();
  for (const { document_key } of docs) {
    presentKeys.add(document_key);
    for (const c of PREFIX_COUNTERS) {
      if (c.match(document_key)) fanoutCounts[c.fanoutId] = (fanoutCounts[c.fanoutId] ?? 0) + 1;
    }
  }
  return { fanoutCounts, presentKeys };
}
```
(Define `PipelineDayData` locally if importing from topology creates a cycle.)

- [ ] **Step 4: Run test → PASS.**

- [ ] **Step 5: Commit** — `feat(olympus): pipeline runtime fan-out data (Surface 1, Task 2)`

---

### Task 3: Pure layout engine

**Files:**
- Create: `frontend/olympus/lib/pipeline-layout.ts`
- Test: `frontend/olympus/lib/pipeline-layout.test.ts`

**Interfaces:**
- Consumes: `PIPELINE_TOPOLOGY`, `StageDef` (Task 1); `PipelineDayData` (Task 2).
- Produces:
  ```ts
  export interface LaidOutNode {
    id: string;            // unique: `${stageId}` | `${stageId}:${subStepId}` | `${stageId}:${subStepId}:${i}`
    kind: 'stage' | 'substep' | 'fanout-branch';
    stageId: PipelineStageId;
    label: string;
    x: number; y: number; width: number; height: number;
    documentKey?: string;  // leaf only
  }
  export interface Connector { fromId: string; toId: string; }
  export interface PipelineLayout { nodes: LaidOutNode[]; connectors: Connector[]; width: number; height: number; }
  export interface ExpansionState { expandedStages: Set<PipelineStageId>; expandedFanouts: Set<string>; }
  export function layoutPipeline(day: PipelineDayData, expansion: ExpansionState): PipelineLayout;
  ```
- Layout rules (assert in tests): collapsed → 5 stage nodes left→right with strictly increasing `x`, equal `y`. Expanding a stage lays its sub-steps horizontally (increasing `x`) within the stage's bracket; downstream stages shift right (no `x` overlap). Expanding a fan-out lays `count` branch nodes vertically (increasing `y`, same `x`) below the sub-step. `width`/`height` are the bounding box (used for Fit).

- [ ] **Step 1: Write the failing test** (collapsed spine + one expansion):

```ts
import { describe, it, expect } from 'vitest';
import { layoutPipeline } from './pipeline-layout';

const emptyDay = { fanoutCounts: { sectors: 12 }, presentKeys: new Set<string>() };
const collapsed = { expandedStages: new Set(), expandedFanouts: new Set<string>() } as any;

describe('layoutPipeline', () => {
  it('collapsed: five stage nodes left to right, same row', () => {
    const l = layoutPipeline(emptyDay as any, collapsed);
    const stages = l.nodes.filter((n) => n.kind === 'stage');
    expect(stages).toHaveLength(5);
    const xs = stages.map((n) => n.x);
    expect([...xs]).toEqual([...xs].sort((a, b) => a - b)); // strictly increasing order preserved
    expect(new Set(stages.map((n) => n.y)).size).toBe(1);   // one row
  });
  it('expanding sectors fan-out emits 12 vertical branch nodes', () => {
    const exp = { expandedStages: new Set(['research']), expandedFanouts: new Set(['research:sectors']) } as any;
    const l = layoutPipeline(emptyDay as any, exp);
    const branches = l.nodes.filter((n) => n.kind === 'fanout-branch' && n.id.startsWith('research:sectors:'));
    expect(branches).toHaveLength(12);
    const ys = branches.map((n) => n.y);
    expect(new Set(branches.map((n) => n.x)).size).toBe(1); // same column
    expect([...ys]).toEqual([...ys].sort((a, b) => a - b)); // stacked downward
  });
});
```

- [ ] **Step 2: Run test → FAIL.**

- [ ] **Step 3: Implement** `layoutPipeline` with a deterministic grid walker: constants `NODE_W`, `NODE_H`, `GAP_X`, `GAP_Y`; advance a cursor `x` per stage; when a stage is expanded, walk its sub-steps advancing `x` by `NODE_W+GAP_X`; for an expanded fan-out, emit `count` branch nodes at the sub-step's `x`, `y = baseY + (i+1)*(NODE_H+GAP_Y)`. Track `maxX`/`maxY` for `width`/`height`. Connector list links consecutive nodes in each axis. Keep it pure and total (no DOM, no clock). Branch node `documentKey` resolved via Task 4's resolver when available; for now derive from presentKeys if the fan-out maps to enumerable keys, else leave undefined.

- [ ] **Step 4: Run test → PASS.**

- [ ] **Step 5: Commit** — `feat(olympus): pure pipeline layout engine (Surface 1, Task 3)`

---

### Task 4: node→document_key resolver + param parse

**Files:**
- Modify: `frontend/olympus/lib/pipeline-links.ts`
- Test: `frontend/olympus/lib/pipeline-links.test.ts`

**Interfaces:**
- Consumes: existing `buildPipelineHref`, `PipelineStage` (already in file — read it first).
- Produces:
  ```ts
  export function parsePipelineParams(sp: URLSearchParams): { date?: string; stage?: PipelineStage; node?: string };
  export function leafDocumentKey(subStepId: string, branch?: string): string | null;
  // maps: 'digest'->'digest', 'pm-direction'->'pm-direction-memo', 'risk-sizing'->'pm-rebalance',
  // 'analysts'+ticker->`analyst/${ticker}`, 'deliberation'+ticker->`deliberation/${ticker}`,
  // 'commit'+runId->`commit-run/${runId}`. Unknown -> null.
  ```

- [ ] **Step 1: Write the failing test**

```ts
import { describe, it, expect } from 'vitest';
import { parsePipelineParams, leafDocumentKey } from './pipeline-links';

describe('pipeline link resolvers', () => {
  it('parses the locked grammar', () => {
    const p = parsePipelineParams(new URLSearchParams('date=2026-06-23&stage=selection&node=analyst/SPY'));
    expect(p).toEqual({ date: '2026-06-23', stage: 'selection', node: 'analyst/SPY' });
  });
  it('maps sub-steps to document_keys', () => {
    expect(leafDocumentKey('pm-direction')).toBe('pm-direction-memo');
    expect(leafDocumentKey('analysts', 'SPY')).toBe('analyst/SPY');
    expect(leafDocumentKey('nope')).toBeNull();
  });
});
```

- [ ] **Step 2: Run test → FAIL.**

- [ ] **Step 3: Implement** both functions in `pipeline-links.ts`. Validate `stage` against the `PipelineStage` union (ignore unknown). Keep `buildPipelineHref` unchanged.

- [ ] **Step 4: Run test → PASS** (and re-run existing `pipeline-links.test.ts` cases).

- [ ] **Step 5: Commit** — `feat(olympus): pipeline node→document_key resolver + param parse (Surface 1, Task 4)`

---

## Phase B — Canvas rendering (sequential; depends on Phase A)

> **Read the mockup first** (`pipeline-mockup.html`). Tests in this phase are static-render smoke only (`renderToStaticMarkup`); interactivity is verified by `npx next build` + visual check against the mockup.

### Task 5: PipelineNode + SVG connectors

**Files:**
- Create: `frontend/olympus/components/pipeline/PipelineNode.tsx`, `components/pipeline/PipelineConnectors.tsx`
- Test: `frontend/olympus/components/pipeline/PipelineNode.test.tsx`

**Interfaces:**
- Consumes: `LaidOutNode`, `Connector` (Task 3).
- Produces: `PipelineNode({ node, count?, expandable, expanded, onActivate })`; `PipelineConnectors({ connectors, nodes })` rendering one `<svg>` with `<path>` per connector (clean orthogonal/curve, no CSS-line approximations).

- [ ] **Step 1: Failing test** — render a single `stage` node via `renderToStaticMarkup`, assert the label text and (for a fan-out) a count badge appear; assert F5 compliance (no `fin-purple`).
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement** node card (glass-card styling, lucide chevron when `expandable`, count badge using `--accent`) + SVG connector layer. Absolute-positioned at `node.x/y` within the canvas coordinate space.
- [ ] **Step 4: PASS.**
- [ ] **Step 5: Commit** — `feat(olympus): pipeline node + SVG connectors (Surface 1, Task 5)`

### Task 6: Camera controller (pan/zoom/fit/auto-center)

**Files:**
- Create: `frontend/olympus/components/pipeline/useCanvasCamera.ts`
- Test: `frontend/olympus/components/pipeline/useCanvasCamera.test.ts` (pure math only)

**Interfaces:**
- Produces: `useCanvasCamera()` → `{ transform, zoomIn, zoomOut, fit(bbox, viewport), centerOn(rect, viewport), bind }`. Extract the pure math into exported helpers `computeFit(bbox, viewport)` and `computeCenter(rect, viewport, scale)` returning `{ x, y, scale }` — test THESE (the hook itself needs DOM, untested here).

- [ ] **Step 1: Failing test** for `computeFit` (a bbox larger than viewport returns scale<1 that fits both axes; centered translate) and `computeCenter` (a node rect maps to viewport center at given scale).
- [ ] **Step 2: FAIL.**
- [ ] **Step 3: Implement** the hook (pointer drag → translate; wheel/buttons → scale clamped `[0.4, 2.5]`; `fit`/`centerOn` set transform; honor `prefers-reduced-motion` by skipping the transition). **Auto-center requirement:** expanding a stage/fan-out calls `centerOn` the new bounding rect (closes mockup gap #1).
- [ ] **Step 4: PASS.**
- [ ] **Step 5: Commit** — `feat(olympus): canvas camera controller w/ auto-center (Surface 1, Task 6)`

### Task 7: PipelineCanvas (composition + expansion state)

**Files:**
- Create: `frontend/olympus/components/pipeline/PipelineCanvas.tsx`
- Test: `frontend/olympus/components/pipeline/PipelineCanvas.test.tsx`

**Interfaces:**
- Consumes: Tasks 1–6.
- Produces: `PipelineCanvas({ day, initialExpansion?, onNodeActivate })` — owns `ExpansionState`, calls `layoutPipeline`, renders connectors + nodes, wires camera (Fit / Expand all / Collapse buttons), clips overflow (`overflow:hidden` viewport; pans within — closes mockup gap #2; page body never scrolls horizontally).

- [ ] **Step 1: Failing test** — static render with collapsed state shows 5 stage labels; `initialExpansion` for `research` shows research sub-step labels.
- [ ] **Step 2: FAIL.** → **Step 3: Implement.** → **Step 4: PASS.**
- [ ] **Step 5: Commit** — `feat(olympus): zoomable pipeline canvas (Surface 1, Task 7)`

### Task 8: PipelineNodeDetail (reuse document views)

**Files:**
- Create: `frontend/olympus/components/pipeline/PipelineNodeDetail.tsx`
- Test: `frontend/olympus/components/pipeline/PipelineNodeDetail.test.tsx`

**Interfaces:**
- Consumes: `lib/hooks/use-library-document.ts` + the `library/*` views. **Do not re-implement rendering** — dispatch on `document_key` to the same view chosen by `LibraryDocumentBody`/`DocumentExpandInline` (read those first to mirror the dispatch).
- Produces: `PipelineNodeDetail({ documentKey, date, onClose })` — desktop: right-side panel; mobile (`< md`): bottom sheet. Empty/missing key → an actionable empty state (not a dead end).

- [ ] **Step 1: Failing test** — static render with a known `document_key` mounts the matching view's container; missing key renders the empty state copy.
- [ ] **Step 2: FAIL.** → **Step 3: Implement** (reuse hook + views; responsive container only). → **Step 4: PASS.**
- [ ] **Step 5: Commit** — `feat(olympus): pipeline node-detail via reused document views (Surface 1, Task 8)`

### Task 9: Summary strip + day selector

**Files:**
- Create: `components/pipeline/PipelineSummaryStrip.tsx`, `components/pipeline/PipelineDaySelector.tsx`
- Test: `components/pipeline/PipelineSummaryStrip.test.tsx`

**Interfaces:**
- Consumes: digest doc + `daily_snapshots` (bias/regime), `decision_log` (the decision) via existing queries.
- Produces: `PipelineSummaryStrip({ headline, regimeChips, decision })` (absorbs "The Read"); `PipelineDaySelector({ dates, value, onChange })` scoping the canvas to a date.

- [ ] **Step 1: Failing test** — strip renders headline + a regime chip + the decision; F5 colors (signed values only in fin-green/red).
- [ ] **Step 2: FAIL.** → **Step 3: Implement.** → **Step 4: PASS.**
- [ ] **Step 5: Commit** — `feat(olympus): pipeline summary strip + day selector (Surface 1, Task 9)`

### Task 10: PipelineClient + route + deep-link hydration

**Files:**
- Create: `components/pipeline/PipelineClient.tsx`
- Replace: `app/pipeline/page.tsx` (remove `/why` redirect)
- Test: `app/pipeline/page.test.ts`

**Interfaces:**
- Consumes: all of Phase A/B; `parsePipelineParams` (Task 4).
- Produces: `PipelineClient` — loads the selected day's docs, builds `PipelineDayData`, derives `initialExpansion` + initial node-detail from URL params (`date`/`stage`/`node`), composes SummaryStrip + DaySelector + Canvas + NodeDetail.

- [ ] **Step 1: Failing test** — `app/pipeline/page.test.ts`: static render mounts the canvas (5 stage labels), and a param `?stage=research` yields research expanded. (Use a fixture day pinned to 2026-06-23 values.)
- [ ] **Step 2: FAIL.** → **Step 3: Implement**; delete the redirect placeholder. → **Step 4: PASS.**
- [ ] **Step 5: Commit** — `feat(olympus): pipeline route + deep-link hydration, retire /why redirect (Surface 1, Task 10)`

---

## Phase C — Integration & polish

### Task 11: Responsive, reduced-motion, no-overflow, suite + build gate

**Files:**
- Modify: any Phase B component needing polish; add `app/pipeline/page.test.ts` cases.

- [ ] **Step 1:** Add tests: page body has no horizontal-scroll class; node-detail uses bottom-sheet classes under `md`.
- [ ] **Step 2:** Verify `prefers-reduced-motion` disables camera/expand transitions (code inspection + the camera helper's motion flag).
- [ ] **Step 3:** Run full gate:
  - `npx vitest run` → all green
  - `npx tsc --noEmit` → no new errors vs baseline (4)
  - `npx next build` → succeeds, `/pipeline` is `○ (Static)` and no longer redirects
  - token-hygiene test green
- [ ] **Step 4:** Manual/visual pass against `pipeline-mockup.html`: collapsed spine, expand stage (horizontal), expand fan-out (vertical), camera auto-centers, leaf opens node-detail, mobile bottom sheet, no overflow.
- [ ] **Step 5: Commit** — `feat(olympus): pipeline graph polish + integration gate (Surface 1, Task 11)`

---

## Self-Review notes (author)

- **Spec coverage:** layout grammar (T3), required behaviors auto-center (T6)/no-overflow (T7)/reduced-motion+responsive (T11), data backbone node→key mapping (T4) + reuse stack (T8), deep-link grammar (T4/T10), Why-absorption: The Read→SummaryStrip+digest node (T9/T8), Deliberations→H6 nodes (T3/T8), Documents→node-detail (T8). Day selector (T9). Covered.
- **Harness honesty:** pan/zoom/camera are not unit-testable here; pure math (`computeFit`/`computeCenter`) and pure layout/topology/resolver ARE — that's where the failing-test-first discipline lands. Rendering tasks use static-render smoke + the build/visual gate.
- **Open follow-ups (NOT in this plan):** develop's `ThesesTab` MiniCalendar date-scrubber and `WhyToday` roll-up were superseded by the second-pass during the merge — revisit only if product wants them re-grafted.
