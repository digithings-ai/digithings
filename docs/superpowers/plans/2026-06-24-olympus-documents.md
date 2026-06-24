---
# Documents Archive Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.
**Goal:** Defer the standalone Documents archive — delete the duplicate per-day reader (`ResearchClient` + Knowledge Base + MiniCalendar/accordion browser), hand the doc-rendering stack to Pipeline untouched, move cross-day discovery into the command palette (document search keyed off `document_key`, deep-linking to Pipeline nodes), repoint stale `/research?...&docKey` links, and leave a one-line faceted-archive stub gated behind `distinct-dates > 1`.
**Architecture:** The doc-rendering stack (`DocumentExpandInline` + `LibraryDocumentBody` + per-type views + `use-library-document`) is shared by Portfolio/AnalysisTab and stays in place — Pipeline (Surface 1, separate build) mounts it. This plan removes the *archive surface* that duplicated it: the 556-line `ResearchClient`, `KnowledgeBasePanel`, and the MiniCalendar/per-date-accordion browse. `research-doc-categorize.ts` and `research-manifest.ts` survive as libs for a future archive but lose their only consumer. Cross-day discovery becomes a pure `buildDocumentSearchItems(docs, query)` helper folded into the Phase-0-re-authored command palette, deep-linking via the locked `buildPipelineHref` grammar.
**Tech Stack:** Next.js 16 static export (`output:export`, `basePath /olympus`), React 19, Tailwind v4 `@theme` tokens, lucide-react, Supabase. Tests are VITEST (node environment, run from `frontend/olympus`).
## Global Constraints
- **Static export:** `output:export`, `basePath /olympus`. No server components with dynamic params beyond the existing `Suspense`+`useSearchParams` pattern. Routes that disappear become client redirects, never 404s.
- **Tailwind v4 tokens only:** dark-first; cyan-phosphor `--accent #3DD6C4`; Instrument Serif `--font-display`; Geist sans/mono; `glass-card`; semantic `text-fin-green/red/amber`; `bg-bg-primary/secondary/glass`; `border-border-subtle`; `text-text-primary/secondary/muted`.
- **F5 token rule (verbatim):** cyan `--accent #3DD6C4` for links/chrome/the single conviction encoding/the live-fresh dot only; `fin-green`/`fin-red` *strictly* for signed financial values; `fin-amber` for caution/stale/carried/mixed-regime; **no gradients** beyond the existing faint regime wash; **no decorative numbering** unless it encodes the system's own priority. (This surface ships almost no new chrome; the rule mostly governs the palette search rows — keep the existing `text-fin-blue` icon convention already in the palette, do not introduce new color literals.)
- **Empty-state discipline:** the faceted-archive stub is gated on a data predicate (`distinct dates > 1`) and **does not render at all** until then — it is *absent*, not narrating its emptiness. Do not ship an empty faceted table or a single-day accordion.
- **Vitest stays green:** the repo's 150+ plumbing tests + page-level tests must pass. New logic is pure functions tested in `lib/` (node env, no jsdom). Page-level tests for deleted surfaces are deleted/updated in the same task that deletes the surface.
- **Conventional commits:** `feat|fix|refactor|chore(olympus): …`. Every change traces to a GitHub issue (note `Fixes #<N>` placeholders where a backend issue must be filed).
- **Lint:** TS — follow existing eslint/prettier conventions in `frontend/olympus` (ruff is Python-only; do not run it here).
---

## Phase 0 dependencies (consumed, NOT defined here)

This surface is **Phase 2**. It assumes Phase 0 (F2 / deep-link grammar) has already landed:

```ts
// lib/pipeline-links.ts  (Phase 0)
export type PipelineStage = 'inputs' | 'research' | 'synthesis' | 'selection' | 'decision';
export function buildPipelineHref(opts: { date?: string | null; stage?: PipelineStage | null; node?: string | null }): string
//   → /pipeline?date=YYYY-MM-DD&stage=<stage>&node=<document_key>  (node url-encoded; empties omitted)
export function stageForDocumentKey(documentKey: string): PipelineStage | null
```
```tsx
// command-palette.tsx  (Phase 0 re-authored it to be Pipeline-native)
export type CmdItem = { id: string; title: string; hint: string; href: string; icon: ElementType<{ size?: number; className?: string }> };
export function buildCommandItems(data): CmdItem[]   // pure builder; base + thesis + recent-run blocks
```
```ts
// app-shell-context.tsx  (Phase 0)
commandPaletteOpen: boolean; openCommandPalette(): void; closeCommandPalette(): void
// lib/nav.ts  (Phase 0)  NAV[2] = { href: '/pipeline', label: 'Pipeline', icon: GitBranch }
// legacy-spa-redirect.tsx (Phase 0) re-pointed the /library and /research→/pipeline redirects
```

**Pre-flight check (do this before Task 1).** Phase 0 may have landed `buildCommandItems`/`buildPipelineHref` or not, depending on merge order. If `lib/pipeline-links.ts` or the `buildCommandItems` export is missing, STOP and surface it — do not redefine the contract here. Verify:

```bash
cd frontend/olympus
test -f lib/pipeline-links.ts && grep -q 'export function buildPipelineHref' lib/pipeline-links.ts && echo "pipeline-links OK" || echo "MISSING pipeline-links — Phase 0 not landed"
grep -q 'export function buildCommandItems' components/command-palette.tsx && echo "buildCommandItems OK" || echo "MISSING buildCommandItems — Phase 0 not landed"
grep -q 'openCommandPalette' components/app-shell-context.tsx && echo "shell palette control OK" || echo "MISSING shell palette control — Phase 0 not landed"
```

If the redirects in `legacy-spa-redirect.tsx` already point `/research`→`/pipeline` (Phase 0 owns that), Task 4 only handles the *callers* that build `/research?...&docKey` hrefs (which Phase 0 did not own).

---

## Real-code grounding (verified 2026-06-24)

- **Live nav uses `/research` + `/library`, not `/why`.** `components/sidebar.tsx` inlines `{ href:'/research', label:'Research', icon: BookOpen }`. `lib/nav.ts` does **not** exist yet (Phase 0 creates it). The archive surface lives at `app/research/ResearchClient.tsx` (556 lines) and `app/library/page.tsx` (redirect to `/research`).
- **The doc-rendering stack is SHARED — do not delete it.** `DocumentExpandInline` is imported by `ResearchClient.tsx`, `KnowledgeBasePanel.tsx`, **and `components/portfolio/tabs/AnalysisTab.tsx`**. `useLibraryDocument` is imported by `ResearchClient.tsx` **and `components/portfolio/PortfolioShellInner.tsx`**. `LibraryDocumentBody` + per-type views are reused by all of them. These stay; Pipeline (Surface 1) mounts them.
- **MiniCalendar is SHARED — do not delete it.** Used by `PortfolioShellInner.tsx`, `AnalysisTab.tsx`, `ThesesTab.tsx`, `ThesesPageInner.tsx` (+ `ResearchClient.tsx`). Only ResearchClient's use goes away.
- **`KnowledgeBasePanel.tsx` is exclusive to ResearchClient** → removable.
- **`research-doc-categorize.ts` / `research-manifest.ts` survive** (spec: kept for a future faceted archive). Their only non-mutual consumers are `ResearchClient.tsx` + `KnowledgeBasePanel.tsx`, both deleted here. The libs become unreferenced-but-retained; a lib-level unit test (Task 1) keeps them alive and green.
- **Stale `/research?...&docKey` link callers Phase 0 did NOT own:**
  - `components/portfolio/theses/ThesisDetailPageInner.tsx:297` — `href={`/research?tab=daily&date=…&docKey=${d.document_key}`}` in "Related PM documents."
  - `lib/portfolio-research-links.ts` `buildResearchStripLinks(...)` returns `{label, docKey}[]` consumed by `PortfolioShellInner.tsx`/`AnalysisTab.tsx` (these stay on Portfolio's own in-page docKey URL state — see Task 4 scoping note).
- **`Doc.path` === `document_key`** (`lib/queries.ts:667 path: d.document_key`). `Doc` has `{ id, date, title, type, phase, category, segment, sector, runType, path }` (`lib/types.ts:254`). Search keys: `path` (document_key, e.g. `analyst/EWT`, `deliberation/IJR`, `sector-tech`, `macro`), `title`, `segment`, `type`.
- **Palette data source:** `useDashboard().data.docs` is `Doc[]`. The Phase-0 palette already filters digests for `recentDateItems`; I add a document-search block built from the same `docs`.
- **Tests are node-env** (`vitest.config.ts` `environment: 'node'`); no jsdom. New tests are pure-function `lib/*.test.ts`.

---

## Task 1: Delete the archive surface (ResearchClient + Knowledge Base + calendar browser); pin the retained libs with a test

**Files:**
- Delete `app/research/ResearchClient.tsx`
- Delete `components/research/KnowledgeBasePanel.tsx`
- Modify `app/research/page.tsx` → becomes a redirect to `/pipeline`
- Modify `app/library/page.tsx` (already a redirect; confirm it lands on `/pipeline` after Phase 0 — adjust if Phase 0 left it pointing at `/research`)
- Create/Modify `lib/research-doc-categorize.test.ts` (Test — pins the retained categorize lib so deleting its only consumer doesn't bit-rot it)
- Keep (do NOT delete): `components/library/MiniCalendar.tsx`, `lib/research-manifest.ts`, `lib/research-doc-categorize.ts`, the entire `components/library/*` rendering stack, `lib/hooks/use-library-document.ts`

**Interfaces:**
- Consumes: `categorizeResearchDoc(d: Doc): string`, `isKnowledgeBaseDoc(d: Doc): boolean`, `isDailyResearchDoc(d: Doc): boolean` (`lib/research-doc-categorize.ts`); `RESEARCH_CATEGORY_ORDER` (readonly tuple).
- Produces: nothing new exported; removes the `/research` archive surface.

**Steps:**

- [ ] Confirm the categorize/manifest libs will be retained and need a guard test. Read `lib/research-doc-categorize.ts` and write a failing test that pins its behavior so it stays green after its UI consumer is deleted. Create `lib/research-doc-categorize.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest';
  import {
    categorizeResearchDoc,
    isKnowledgeBaseDoc,
    isDailyResearchDoc,
    RESEARCH_CATEGORY_ORDER,
  } from './research-doc-categorize';
  import type { Doc } from './types';

  function doc(partial: Partial<Doc>): Doc {
    return {
      id: 'x', date: '2026-06-23', title: '', type: null, phase: null,
      category: null, segment: null, sector: null, runType: null, path: '',
      ...partial,
    };
  }

  describe('research-doc-categorize (retained for future faceted archive)', () => {
    it('routes the digest to Digest', () => {
      expect(categorizeResearchDoc(doc({ path: 'digest' }))).toBe('Digest');
    });
    it('routes per-ticker analyst docs to Intelligence', () => {
      expect(categorizeResearchDoc(doc({ path: 'analyst/EWT' }))).toBe('Intelligence');
    });
    it('routes macro/asset-class segments to Market Analysis', () => {
      expect(categorizeResearchDoc(doc({ path: 'macro', segment: 'macro' }))).toBe('Market Analysis');
    });
    it('marks deep dives as knowledge-base docs, daily research otherwise', () => {
      const deepDive = doc({ path: 'research/deep-dives/ai-capex', category: 'deep-dive' });
      expect(isKnowledgeBaseDoc(deepDive)).toBe(true);
      expect(isDailyResearchDoc(deepDive)).toBe(false);
      expect(isDailyResearchDoc(doc({ path: 'digest' }))).toBe(true);
    });
    it('keeps Digest first in the category order', () => {
      expect(RESEARCH_CATEGORY_ORDER[0]).toBe('Digest');
    });
  });
  ```
- [ ] Run it — expect PASS already (this is a characterization test of existing behavior; if any case FAILS the lib differs from the spec's understanding — stop and reconcile):
  ```bash
  cd frontend/olympus && npx vitest run lib/research-doc-categorize.test.ts
  ```
- [ ] Delete the archive surface and its exclusive child:
  ```bash
  cd frontend/olympus && git rm app/research/ResearchClient.tsx components/research/KnowledgeBasePanel.tsx
  ```
- [ ] Rewrite `app/research/page.tsx` to a client redirect to `/pipeline` (no surface to render anymore). Replace the entire file:
  ```tsx
  // Old `/research` archive surface is retired (Documents deferred behind distinct-dates > 1).
  // Per-day reading now lives in Pipeline node-detail; this route redirects there.
  import { ResearchToPipelineRedirectPage } from '@/components/legacy-spa-redirect';

  export default ResearchToPipelineRedirectPage;
  ```
- [ ] Verify `app/library/page.tsx` lands on `/pipeline`. Read it; if it still re-exports `LibraryToResearchRedirectPage` (i.e. Phase 0 did not retarget it), it now forwards to a redirect-to-`/pipeline` — acceptable (one hop). If Phase 0 added a `LibraryToPipelineRedirectPage`, switch the import to it. Do not introduce a new redirect component here if Phase 0 already owns one (Task 4 adds `ResearchToPipelineRedirectPage` if it is missing).
- [ ] Build-check that nothing else imported the deleted files (the grep below must be empty):
  ```bash
  cd frontend/olympus && grep -rn "ResearchClient\|KnowledgeBasePanel" --include="*.tsx" --include="*.ts" . | grep -v node_modules
  ```
- [ ] Confirm the retained shared components still have live importers (must each print ≥1 NON-deleted caller — Portfolio/AnalysisTab):
  ```bash
  cd frontend/olympus && grep -rln "DocumentExpandInline\|useLibraryDocument\|library/MiniCalendar" --include="*.tsx" --include="*.ts" . | grep -v node_modules
  ```
- [ ] Run the full suite to confirm no page-level test referenced the deleted surface (none does per the test inventory, but confirm):
  ```bash
  cd frontend/olympus && npx vitest run
  ```
- [ ] Commit:
  ```bash
  cd frontend/olympus && git add -A && git commit -m "refactor(olympus): retire the Documents archive surface (defer behind distinct-dates>1)

Delete ResearchClient (556-line MiniCalendar + carry-forward browser) and the
empty Knowledge Base tab; /research and /library redirect to /pipeline. Per-day
reading now lives in Pipeline node-detail (shared doc-rendering stack untouched).
research-doc-categorize/manifest libs retained for a future faceted archive and
pinned by a new lib test.

Fixes #<DOCS-ARCHIVE-ISSUE>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JvfyP2WatQhVSBS45HPys2"
  ```

---

## Task 2: Cross-day document search — pure `buildDocumentSearchItems(docs, query)` helper

**Files:**
- Create `lib/document-search.ts`
- Create `lib/document-search.test.ts` (Test)

**Interfaces:**
- Consumes: `Doc` (`lib/types.ts`); `buildPipelineHref` + `stageForDocumentKey` (`lib/pipeline-links.ts`, Phase 0).
- Produces:
  ```ts
  export interface DocumentSearchItem {
    id: string;          // `doc-${doc.id}` — stable, palette-unique
    title: string;       // canonical-ish display name
    hint: string;        // `${date} · ${stageLabel}` provenance
    href: string;        // buildPipelineHref({ date, stage, node: document_key })
  }
  export function buildDocumentSearchItems(docs: Doc[], query: string, limit?: number): DocumentSearchItem[]
  ```
  `buildCommandItems` (Task 3) appends these. `limit` defaults to 8 (palette stays scannable).

**Why a separate pure module:** the palette is a `'use client'` React component tested only via node-env pure functions. Keeping the matcher in `lib/` lets us TDD ranking/deep-linking without a DOM.

**Steps:**

- [ ] Write the failing test first. Create `lib/document-search.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest';
  import { buildDocumentSearchItems } from './document-search';
  import type { Doc } from './types';

  function doc(partial: Partial<Doc>): Doc {
    return {
      id: 'x', date: '2026-06-23', title: '', type: null, phase: null,
      category: null, segment: null, sector: null, runType: null, path: '',
      ...partial,
    };
  }

  describe('buildDocumentSearchItems', () => {
    const docs: Doc[] = [
      doc({ id: '1', path: 'analyst/EWT', title: 'EWT analyst', date: '2026-06-23', segment: 'analyst' }),
      doc({ id: '2', path: 'deliberation/IJR', title: 'IJR deliberation', date: '2026-06-23', segment: 'deliberation' }),
      doc({ id: '3', path: 'sector-tech', title: 'Technology sector', date: '2026-06-23', segment: 'sector', sector: 'tech' }),
      doc({ id: '4', path: 'macro', title: 'Macro outlook', date: '2026-06-23', segment: 'macro' }),
    ];

    it('returns nothing for a blank query (search is keyed, not a dump)', () => {
      expect(buildDocumentSearchItems(docs, '')).toEqual([]);
      expect(buildDocumentSearchItems(docs, '   ')).toEqual([]);
    });

    it('matches a ticker against the document_key (path) case-insensitively', () => {
      const out = buildDocumentSearchItems(docs, 'ewt');
      expect(out).toHaveLength(1);
      expect(out[0].id).toBe('doc-1');
      // Deep-links to the Pipeline node via the locked grammar (node = document_key, url-encoded).
      expect(out[0].href).toContain('/pipeline?');
      expect(out[0].href).toContain('date=2026-06-23');
      expect(out[0].href).toContain('node=analyst%2FEWT');
      // analyst/* maps to the selection stage (stageForDocumentKey contract).
      expect(out[0].href).toContain('stage=selection');
    });

    it('matches a segment word across multiple docs', () => {
      const out = buildDocumentSearchItems(docs, 'sector');
      expect(out.map((i) => i.id)).toContain('doc-3');
    });

    it('matches against the title', () => {
      const out = buildDocumentSearchItems(docs, 'outlook');
      expect(out.map((i) => i.id)).toEqual(['doc-4']);
    });

    it('ranks document_key-prefix matches above mid-string matches', () => {
      const mixed: Doc[] = [
        doc({ id: 'a', path: 'sector-tech', title: 'Technology', segment: 'sector' }),
        doc({ id: 'b', path: 'analyst/SECTORS-ETF', title: 'Sectors ETF analyst', segment: 'analyst' }),
      ];
      const out = buildDocumentSearchItems(mixed, 'sector');
      expect(out[0].id).toBe('doc-a'); // path starts with the query
    });

    it('carries date + stage provenance in the hint', () => {
      const out = buildDocumentSearchItems(docs, 'macro');
      expect(out[0].hint).toContain('2026-06-23');
      expect(out[0].hint.toLowerCase()).toContain('research'); // macro → research stage
    });

    it('honors the limit', () => {
      const many: Doc[] = Array.from({ length: 20 }, (_, i) =>
        doc({ id: String(i), path: `analyst/T${i}`, title: `T${i} analyst`, segment: 'analyst' })
      );
      expect(buildDocumentSearchItems(many, 'analyst', 5)).toHaveLength(5);
    });
  });
  ```
- [ ] Run it — expect FAIL (module does not exist):
  ```bash
  cd frontend/olympus && npx vitest run lib/document-search.test.ts
  ```
- [ ] Implement `lib/document-search.ts` with the real matcher + deep-link build:
  ```ts
  import type { Doc } from '@/lib/types';
  import { buildPipelineHref, stageForDocumentKey, type PipelineStage } from '@/lib/pipeline-links';

  export interface DocumentSearchItem {
    id: string;
    title: string;
    hint: string;
    href: string;
  }

  const STAGE_LABEL: Record<PipelineStage, string> = {
    inputs: 'Inputs',
    research: 'Research',
    synthesis: 'Synthesis',
    selection: 'Selection',
    decision: 'Decision',
  };

  /** Human-ish display name for a doc when its title is thin (falls back to the document_key). */
  function displayTitle(d: Doc): string {
    const t = (d.title || '').trim();
    if (t) return t;
    return d.path || d.segment || 'Document';
  }

  /** Rank: document_key-prefix (0) < title-prefix (1) < any substring match (2). Lower is better. */
  function rank(d: Doc, q: string): number | null {
    const path = (d.path || '').toLowerCase();
    const title = (d.title || '').toLowerCase();
    const segment = (d.segment || '').toLowerCase();
    const type = (d.type || '').toLowerCase();
    if (path.startsWith(q)) return 0;
    if (title.startsWith(q)) return 1;
    if (path.includes(q) || title.includes(q) || segment.includes(q) || type.includes(q)) return 2;
    return null;
  }

  /**
   * Cross-day document discovery for the command palette. Matches a ticker/segment/title query
   * against `documents` and deep-links each hit to its Pipeline node (locked grammar, F2).
   * Returns `[]` for a blank query — search is keyed, never a full dump.
   */
  export function buildDocumentSearchItems(docs: Doc[], query: string, limit = 8): DocumentSearchItem[] {
    const q = query.trim().toLowerCase();
    if (!q) return [];

    const scored: { doc: Doc; r: number }[] = [];
    for (const d of docs) {
      if (!d.path) continue;
      const r = rank(d, q);
      if (r === null) continue;
      scored.push({ doc: d, r });
    }

    scored.sort((a, b) => {
      if (a.r !== b.r) return a.r - b.r;
      // Stable secondary sort: most recent date first, then title.
      const dateCmp = (b.doc.date || '').localeCompare(a.doc.date || '');
      if (dateCmp !== 0) return dateCmp;
      return displayTitle(a.doc).localeCompare(displayTitle(b.doc));
    });

    return scored.slice(0, limit).map(({ doc: d }) => {
      const stage = stageForDocumentKey(d.path);
      const stageLabel = stage ? STAGE_LABEL[stage] : 'Document';
      return {
        id: `doc-${d.id}`,
        title: displayTitle(d),
        hint: `${d.date} · ${stageLabel}`,
        href: buildPipelineHref({ date: d.date, stage, node: d.path }),
      };
    });
  }
  ```
- [ ] Run it — expect PASS:
  ```bash
  cd frontend/olympus && npx vitest run lib/document-search.test.ts
  ```
- [ ] Commit:
  ```bash
  cd frontend/olympus && git add lib/document-search.ts lib/document-search.test.ts && git commit -m "feat(olympus): cross-day document search for the command palette

buildDocumentSearchItems(docs, query) matches ticker/segment/title against
documents and deep-links each hit to its Pipeline node via the locked grammar.
Degrades perfectly to a single day; blank query returns nothing (keyed search,
not a dump). Replaces the deleted archive's cross-day browse.

Fixes #<DOCS-ARCHIVE-ISSUE>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JvfyP2WatQhVSBS45HPys2"
  ```

---

## Task 3: Wire document search into the command palette

**Files:**
- Modify `components/command-palette.tsx`
- Create/Modify `components/command-palette.test.ts` (Test — pure-builder test; node env, no DOM)

**Interfaces:**
- Consumes: `buildDocumentSearchItems(docs, query, limit?)` (Task 2); `buildCommandItems(data)` + `CmdItem` (Phase 0 palette); `useDashboard().data.docs` (`Doc[]`).
- Produces: the palette's filtered list now includes live document hits when the query is non-empty.

**Design note — how search composes with the existing palette.** The Phase-0 palette filters a static `items` list (base nav + thesis + recent-run blocks) by substring. Document hits are **query-dependent and dynamic** (8 of potentially 71+ docs), so they must NOT join the static `items` list (which `buildCommandItems` builds once). Instead, compute them inside the `filtered` memo from the live query and **append** them after the static matches. This keeps `buildCommandItems` pure and unchanged, and keeps the document block from polluting the empty-query view.

**Steps:**

- [ ] Read the Phase-0 `components/command-palette.tsx` to confirm the `buildCommandItems` export shape and the `filtered` memo. (The pre-Phase-0 file computes `items` inline; after Phase 0 it is `const items = useMemo(() => buildCommandItems(data), [data])`.) Confirm `CmdItem` is exported.
- [ ] Write the failing pure-builder test. Because document search is composed in the component's `filtered` memo, extract that composition into a tiny pure helper so it is node-testable. Add to `components/command-palette.tsx` (exported, next to `buildCommandItems`):
  ```tsx
  /** Filter the static command list by query, then append live document hits (Task 2). */
  export function filterCommandItems(items: CmdItem[], docs: Doc[], query: string): CmdItem[] {
    const qq = query.trim().toLowerCase();
    const staticMatches = !qq
      ? items
      : items
          .filter(
            (i) =>
              i.title.toLowerCase().includes(qq) ||
              i.hint.toLowerCase().includes(qq) ||
              i.id.toLowerCase().includes(qq)
          )
          .sort((a, b) => {
            const aStarts = a.title.toLowerCase().startsWith(qq) ? 0 : 1;
            const bStarts = b.title.toLowerCase().startsWith(qq) ? 0 : 1;
            return aStarts - bStarts;
          });
    if (!qq) return staticMatches;
    const docItems: CmdItem[] = buildDocumentSearchItems(docs, query).map((d) => ({
      id: d.id,
      title: d.title,
      hint: d.hint,
      href: d.href,
      icon: FileText,
    }));
    return [...staticMatches, ...docItems];
  }
  ```
  Create `components/command-palette.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest';
  import { filterCommandItems } from './command-palette';
  import type { Doc } from '@/lib/types';

  type CmdItem = { id: string; title: string; hint: string; href: string; icon: unknown };

  const baseItems: CmdItem[] = [
    { id: 'go-home', title: 'Today', hint: 'Dashboard home', href: '/', icon: null },
    { id: 'go-pipeline', title: 'Pipeline', hint: 'Daily decision graph', href: '/pipeline', icon: null },
  ];

  function doc(partial: Partial<Doc>): Doc {
    return {
      id: 'x', date: '2026-06-23', title: '', type: null, phase: null,
      category: null, segment: null, sector: null, runType: null, path: '',
      ...partial,
    };
  }
  const docs: Doc[] = [
    doc({ id: '1', path: 'analyst/EWT', title: 'EWT analyst', segment: 'analyst' }),
  ];

  describe('filterCommandItems', () => {
    it('returns the static list unchanged for a blank query (no doc dump)', () => {
      expect(filterCommandItems(baseItems, docs, '')).toEqual(baseItems);
    });
    it('appends matching document hits after static matches', () => {
      const out = filterCommandItems(baseItems, docs, 'ewt');
      const docHit = out.find((i) => i.id === 'doc-1');
      expect(docHit).toBeTruthy();
      expect(docHit!.href).toContain('/pipeline?');
      expect(docHit!.href).toContain('node=analyst%2FEWT');
    });
    it('keeps static nav matches ahead of document hits', () => {
      const out = filterCommandItems(baseItems, docs, 'pipeline');
      expect(out[0].id).toBe('go-pipeline');
    });
  });
  ```
- [ ] Run it — expect FAIL (`filterCommandItems` not exported yet):
  ```bash
  cd frontend/olympus && npx vitest run components/command-palette.test.ts
  ```
- [ ] Implement in `components/command-palette.tsx`:
  - Add imports at the top: `import { FileText } from 'lucide-react';` (add to the existing lucide import block if not present) and `import type { Doc } from '@/lib/types';` and `import { buildDocumentSearchItems } from '@/lib/document-search';`.
  - Add the `filterCommandItems` export shown above (place it directly under the `buildCommandItems` export).
  - Replace the component's inline `filtered` memo with a call to the helper so the component and the test share one code path:
    ```tsx
    const docs = useMemo<Doc[]>(() => data?.docs ?? [], [data]);
    const filtered = useMemo(() => filterCommandItems(items, docs, q), [items, docs, q]);
    ```
    (Remove the old inline filter/sort block that this replaces.)
- [ ] Run it — expect PASS:
  ```bash
  cd frontend/olympus && npx vitest run components/command-palette.test.ts
  ```
- [ ] Update the palette input placeholder so document search is discoverable. Change the search `<input>` `placeholder` from the Phase-0 value to:
  ```tsx
  placeholder="Jump to a page, thesis, or document (ticker / segment)…"
  ```
- [ ] Run the full suite (the palette change is shared shell — confirm nothing else broke):
  ```bash
  cd frontend/olympus && npx vitest run
  ```
- [ ] Commit:
  ```bash
  cd frontend/olympus && git add components/command-palette.tsx components/command-palette.test.ts && git commit -m "feat(olympus): palette searches documents by ticker/segment, deep-links to Pipeline

filterCommandItems appends live document hits (buildDocumentSearchItems) after
the static command matches when the query is non-empty. Cross-day discovery for
the deferred Documents archive now lives in the palette; each hit deep-links to
its Pipeline node via the locked grammar.

Fixes #<DOCS-ARCHIVE-ISSUE>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JvfyP2WatQhVSBS45HPys2"
  ```

---

## Task 4: Repoint stale `/research?...&docKey` deep-links to the Pipeline node grammar

**Files:**
- Modify `components/portfolio/theses/ThesisDetailPageInner.tsx` (line ~297, "Related PM documents" links)
- Modify `components/legacy-spa-redirect.tsx` — add `ResearchToPipelineRedirectPage` **only if Phase 0 did not already retarget `/research`** (the pre-flight check tells you; if Phase 0 owns it, skip the redirect edit and only fix the caller below)
- Test: covered by Task 2's `buildPipelineHref` usage; no new test (the link is a thin call to the Phase-0-tested `buildPipelineHref`).

**Scoping note — what this task does NOT touch.** `lib/portfolio-research-links.ts` `buildResearchStripLinks` and `PortfolioShellInner.tsx`'s `docKey` URL-state are **Portfolio's own in-page document drawer** (the AnalysisTab opens docs inline via `useLibraryDocument`, still valid post-defer because the rendering stack stays). Those are NOT stale `/research` links — they manage `?docKey=` on `/portfolio` itself. Leave them; they are owned by the Holdings/Theses surfaces (Phase 1/2 of those surfaces), not Documents.

**Interfaces:**
- Consumes: `buildPipelineHref({ date, stage, node })` + `stageForDocumentKey` (`lib/pipeline-links.ts`, Phase 0).

**Steps:**

- [ ] Read `components/portfolio/theses/ThesisDetailPageInner.tsx` around the "Related PM documents" block (the `relatedDocs.map`, ~line 290–306). Confirm `d.document_key` and `d.date` are available on each related doc.
- [ ] Add the import (top of file, with the other `@/lib` imports):
  ```tsx
  import { buildPipelineHref, stageForDocumentKey } from '@/lib/pipeline-links';
  ```
- [ ] Replace the stale `href`:
  ```tsx
  // BEFORE
  href={`/research?tab=daily&date=${encodeURIComponent(d.date)}&docKey=${encodeURIComponent(d.document_key)}`}
  // AFTER
  href={buildPipelineHref({
    date: d.date,
    stage: stageForDocumentKey(d.document_key),
    node: d.document_key,
  })}
  ```
- [ ] If the pre-flight check showed Phase 0 did NOT retarget `/research`, add `ResearchToPipelineRedirectPage` to `components/legacy-spa-redirect.tsx` so `app/research/page.tsx` (Task 1) has a target. Append after the existing `LibraryToResearchRedirectPage`:
  ```tsx
  /** Old `/research` archive URLs → Pipeline (defer behind distinct-dates>1). Preserve date/docKey → date/node. */
  function ResearchToPipelineInner() {
    const router = useRouter();
    const searchParams = useSearchParams();
    useEffect(() => {
      const date = searchParams.get('date');
      const docKey = searchParams.get('docKey');
      const href = buildPipelineHref({
        date,
        stage: docKey ? stageForDocumentKey(docKey) : null,
        node: docKey,
      });
      router.replace(href);
    }, [router, searchParams]);
    return <RedirectFallback />;
  }
  export function ResearchToPipelineRedirectPage() {
    return (
      <Suspense fallback={<RedirectFallback />}>
        <ResearchToPipelineInner />
      </Suspense>
    );
  }
  ```
  Add at the top of the file: `import { buildPipelineHref, stageForDocumentKey } from '@/lib/pipeline-links';`. Also retarget `LibraryToResearchInner` to forward to `/pipeline` directly (so `/library` is one hop, not two) by replacing its body with the same `buildPipelineHref({ date, stage, node: docKey })` form, and rename the export to `LibraryToPipelineRedirectPage` (update `app/library/page.tsx`'s import). **If Phase 0 already did all of this, skip this whole step.**
- [ ] Verify no `/research?` or `&docKey=` hrefs remain outside Portfolio's own in-page state (the grep should show only `PortfolioShellInner.tsx` / `portfolio-research-links.ts` / `portfolio-url-state.ts` — all intentional in-page Portfolio state, NOT cross-surface navigation):
  ```bash
  cd frontend/olympus && grep -rn "/research?\|docKey=" --include="*.tsx" --include="*.ts" . | grep -v node_modules | grep -v "buildResearchStripLinks\|PortfolioShellInner\|portfolio-url-state"
  ```
- [ ] Run the full suite:
  ```bash
  cd frontend/olympus && npx vitest run
  ```
- [ ] Commit:
  ```bash
  cd frontend/olympus && git add -A && git commit -m "fix(olympus): repoint thesis 'Related PM documents' links to Pipeline nodes

ThesisDetailPageInner's related-doc links used the retired /research?...&docKey
form; rebuild them with buildPipelineHref + stageForDocumentKey so they open the
document's Pipeline node (locked grammar). Add a /research→/pipeline redirect
that maps date/docKey → date/node if Phase 0 left that route on /research.

Fixes #<DOCS-ARCHIVE-ISSUE>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JvfyP2WatQhVSBS45HPys2"
  ```

---

## Task 5: Leave the one-line faceted-archive stub gated behind `distinct-dates > 1`

**Files:**
- Create `lib/document-archive-gate.ts`
- Create `lib/document-archive-gate.test.ts` (Test)

**Interfaces:**
- Consumes: `Doc` (`lib/types.ts`).
- Produces:
  ```ts
  /** True only when the documents span more than one run date — the predicate that
   *  would un-defer a future faceted cross-day archive. Until then the archive is ABSENT. */
  export function shouldShowDocumentArchive(docs: Doc[]): boolean
  ```

**Design note — why a gate function and not a component.** The spec says leave a *one-line stub* gated behind `distinct-dates > 1` that "does not render until then." On today's single-day DB the predicate is `false`, so there is no UI to build and no empty-state to ship (empty-state discipline: absent, not narrating). Shipping the **predicate** (unit-tested) is the credible stub: it is the exact, named condition a future archive route would gate on, with the data check already correct and tested. No route, no component, no nav entry is added this cycle. A short doc comment records the deferral decision for the next author.

**Steps:**

- [ ] Write the failing test. Create `lib/document-archive-gate.test.ts`:
  ```ts
  import { describe, expect, it } from 'vitest';
  import { shouldShowDocumentArchive } from './document-archive-gate';
  import type { Doc } from './types';

  function doc(date: string, id: string): Doc {
    return {
      id, date, title: '', type: null, phase: null, category: null,
      segment: null, sector: null, runType: null, path: `analyst/${id}`,
    };
  }

  describe('shouldShowDocumentArchive (faceted archive deferral gate)', () => {
    it('is false on the baseline single-day world (archive stays absent)', () => {
      expect(shouldShowDocumentArchive([doc('2026-06-23', 'a'), doc('2026-06-23', 'b')])).toBe(false);
    });
    it('is false with no documents', () => {
      expect(shouldShowDocumentArchive([])).toBe(false);
    });
    it('un-defers once documents span more than one distinct date', () => {
      expect(shouldShowDocumentArchive([doc('2026-06-23', 'a'), doc('2026-06-24', 'b')])).toBe(true);
    });
    it('ignores docs with no date when counting distinct dates', () => {
      const noDate = doc('', 'c');
      expect(shouldShowDocumentArchive([doc('2026-06-23', 'a'), noDate])).toBe(false);
    });
  });
  ```
- [ ] Run it — expect FAIL (module missing):
  ```bash
  cd frontend/olympus && npx vitest run lib/document-archive-gate.test.ts
  ```
- [ ] Implement `lib/document-archive-gate.ts`:
  ```ts
  import type { Doc } from '@/lib/types';

  /**
   * Faceted cross-day Documents archive — DEFERRED this cycle (2026-06-24 redesign).
   *
   * The standalone archive (MiniCalendar + per-date accordion + carry-forward manifest)
   * was retired because the live DB holds a single day; per-day reading lives in Pipeline
   * node-detail and cross-day discovery lives in the command palette
   * (`buildDocumentSearchItems`). A future faceted archive should gate its route/nav entry
   * on THIS predicate — until documents span more than one date it must not render at all
   * (empty-state discipline: absent, not narrating its emptiness).
   *
   * When this flips true, rebuild the archive over `research-doc-categorize.ts`
   * (`categorizeResearchDoc` / `RESEARCH_CATEGORY_ORDER`), which were retained for exactly this.
   */
  export function shouldShowDocumentArchive(docs: Doc[]): boolean {
    const dates = new Set<string>();
    for (const d of docs) {
      if (d.date) dates.add(d.date);
    }
    return dates.size > 1;
  }
  ```
- [ ] Run it — expect PASS:
  ```bash
  cd frontend/olympus && npx vitest run lib/document-archive-gate.test.ts
  ```
- [ ] Final full-suite run to confirm the whole Documents surface is green:
  ```bash
  cd frontend/olympus && npx vitest run
  ```
- [ ] Commit:
  ```bash
  cd frontend/olympus && git add lib/document-archive-gate.ts lib/document-archive-gate.test.ts && git commit -m "chore(olympus): credible deferral stub for the faceted Documents archive

shouldShowDocumentArchive(docs) is the named, unit-tested predicate a future
cross-day archive gates on (distinct dates > 1). False on today's single-day DB,
so nothing renders — the archive is absent, not an empty table. Documents the
deferral and points the next author at the retained categorize lib.

Fixes #<DOCS-ARCHIVE-ISSUE>

Co-Authored-By: Claude Opus 4.8 (1M context) <noreply@anthropic.com>
Claude-Session: https://claude.ai/code/session_01JvfyP2WatQhVSBS45HPys2"
  ```

---

## GitHub issues to file (DigiThings convention)

This surface is a single frontend-issue's worth of work; the `Fixes #<DOCS-ARCHIVE-ISSUE>` placeholder above is one issue ("Olympus Documents — defer the archive, hand reading to Pipeline, palette cross-day search"). It depends on the **F2 / deep-link-grammar Phase 0 issue** (`buildPipelineHref`, `buildCommandItems`, nav flip) landing first. No *backend* issue originates here — the four backend issues in the spec (`weight_pct` seeding, `backtest-seed`, `thesis_id` canonicalization, `linked_market_thesis_id`) belong to Holdings/Theses/Performance, not Documents.

## Risks / sequencing

- **Hard dependency on Phase 0.** Tasks 2–4 consume `buildPipelineHref`/`stageForDocumentKey`/`buildCommandItems`/the nav flip. The pre-flight check in Task 1 gates the whole plan; if Phase 0 is not merged, stop.
- **Do not delete shared code.** MiniCalendar (4 other callers) and the entire `components/library/*` rendering stack + `use-library-document` (Portfolio/AnalysisTab callers) must survive — only `ResearchClient` + `KnowledgeBasePanel` are deleted. The Task 1 grep checks guard this.
- **Redirect ownership overlap with Phase 0/F2.** F2 retargets the `/library` and `/research` redirects. Task 1 and Task 4 are written to *detect* whether Phase 0 already did this and avoid double-editing; if both touch `legacy-spa-redirect.tsx` there may be a trivial merge conflict — resolve by keeping the `/pipeline`-targeting version.
