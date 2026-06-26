---
# Performance tear sheet Implementation Plan
> **For agentic workers:** REQUIRED SUB-SKILL: superpowers:subagent-driven-development or superpowers:executing-plans. Steps use checkbox (- [ ]) syntax.
**Goal:** Ship a hybrid, exportable Performance tear sheet for the single strategy "Olympus" at `/portfolio/performance` — a live-NAV track + an Olympus-specific decision track-record track, each degrading independently, empty-state-first, on one `window.print()` page.
**Architecture:** Port the dependency-free digiquant tear-sheet template (`frontend/digiquant-web/components/tearsheet/*` + its `.ts-*` print/chart CSS) into Olympus by copying the `charts.tsx` / `format.ts` SVG primitives and the `.ts-*` CSS block into Olympus's `app/globals.css` (every CSS var the template uses — `--up`, `--down`, `--ink`, `--hair`, `--accent`, `--surface`, `--r-md`, `--ease` — is already declared in the shared `@digithings/design/tokens.css` that Olympus imports, with the cyan `--accent #3DD6C4`, so the "token bridge" is an equivalence, not a remap: `--up`≡`--color-fin-green`, `--down`≡`--color-fin-red`, `--ink`≡`--color-text-primary`, `--hair`≡`--color-border-subtle`). A new `OlympusTearsheet` TS type wraps the existing `TearsheetData` (engine `'live'`) plus a new `DecisionTrackRecord` computed **client-side** in `lib/decision-track-record.ts` (a faithful port of `digiquant/.../atlas/backtest.py`'s pure functions, covered by a vitest parity test). Data comes from a new fail-soft `fetchOlympusTearsheet()` in `lib/observability-queries.ts` reading `nav_history` + `decision_log` + `portfolio_metrics` + `position_attribution`. The page absorbs the Attribution diagnostics relocated from System.
**Tech Stack:** Next.js 16 static export (`output:export`, `basePath /olympus`), React 19, Tailwind v4 (`@theme` tokens, `[data-theme]`), pure-SVG charts (no recharts in the tear sheet), lucide-react, `@supabase/supabase-js`, vitest.

## Global Constraints
- **Static export only.** No server components with runtime data, no route handlers, no SSR fetch. Data loads client-side in a `'use client'` page via `useEffect` + the Supabase anon client (mirror `app/system/page.tsx`). The page sits under `/portfolio/performance`; AppFrame chrome wraps it automatically.
- **Tailwind v4 `@theme` tokens only.** Use the existing semantic utilities (`text-fin-green/red/amber`, `bg-bg-primary/secondary`, `border-border-subtle`, `text-text-primary/secondary/muted`, `font-display`) and the ported `.ts-*` classes. No new color literals.
- **vitest, kept green.** `npm test` (which runs `vitest run`) from `frontend/olympus` must stay green. The 150+ plumbing tests and page-level tests must not regress; page-level tests are updated as part of this work. New logic ships with a failing-first test.
- **The F5 token rule (verbatim):** cyan `--accent #3DD6C4` for links/chrome/the single conviction encoding/the live-fresh dot only; `fin-green`/`fin-red` *strictly* for signed financial values; `fin-amber` for caution/stale/carried/mixed-regime; **no gradients** beyond the existing faint regime wash; **no decorative numbering** unless it encodes the system's own priority. The ported `.ts-*` CSS already obeys this (`--up`/`--down` for signed values, `--accent` for chrome/links only). The KPI rail is **one keystroke from the MetricCard wall it replaces** — single headline KPI, strict hierarchy, no equal-weight 2×4 grid.
- **Empty-state discipline (verbatim):** time-series elements are gated on a data predicate (≥2 NAV points; ≥1 resolved decision) and render a calm, *element-specific* line — never an em-dash placeholder, a 1-row "table over time," or a single-dot chart. Live-NAV <2 rows → an "inception" card ("NAV 99.32 — live since 2026-06-23 — equity curve accrues daily"); decision track 0 resolved → "11 decisions in flight — track record resolves as holding windows close." **PDF export stays enabled in all states.** The D2 backtest-seed is what makes these populated for demos; until then the empty states are the honest default.
- **Slop guard:** do not stamp the System Zone1/Zone2 or Today hero/band composition here. This surface's structure is driven by its data shape: one serif H1 → one primary KPI strip → two labeled `.ts-panel` tracks. The conviction-calibration chart must encode a *different real quantity* (mean alpha per conviction bucket) from the per-decision alpha chart.
- **Issue linkage:** every commit traces to a GitHub issue. The Phase-0 backend issues are referenced as `Fixes #<N>` placeholders where the data this surface needs is seeded upstream (the `backtest-seed` D2 issue gates the populated state; file it if not already filed).

---

### Task 1: Backtest parity port — `lib/decision-track-record.ts` (+ vitest parity test)

The differentiating metric layer. A faithful TS port of `digiquant/src/digiquant/olympus/atlas/backtest.py`'s pure functions, producing `DecisionTrackRecord`. This is the only place the decision metrics are computed; the page consumes it. The existing `lib/decision-scorecard.ts` stays as-is for the calibration *bucket* shape (Task 4 reuses its `convictionBucketCalibration`); this file adds the track-record aggregate (`information_ratio`, `sortino_ratio`, `max_drawdown_pct`, `mean/median_alpha_pct`, `hit_rate`, `n_trades`) that `decision-scorecard.ts` does not produce.

**Files:**
- Create `frontend/olympus/lib/decision-track-record.ts`
- Test: `frontend/olympus/lib/decision-track-record.test.ts`

**Interfaces:**
- Consumes: nothing from Phase 0 directly (pure). Input shape mirrors the resolved `decision_log` row fields (`alpha` fraction, `actual_return` fraction, `conviction`, `run_date`, `holding_days`, `status`).
- Produces (the Phase 0 contract's Phase-3 sketch, defined concretely here):
  ```ts
  export interface ConvictionBucketStat { conviction: number; mean_alpha_pct: number; n: number }
  export interface DecisionTrackRecord {
    n_trades: number;
    hit_rate: number;            // 0..1, share with positive alpha
    mean_alpha_pct: number;
    median_alpha_pct: number;
    information_ratio: number;   // mean(alpha)/std(alpha), per-decision (NOT annualized)
    sortino_ratio: number;       // mean(alpha)/downside-std; falls back to info ratio if no downside
    max_drawdown_pct: number;    // worst peak-to-trough of the decision equity curve
    conviction_buckets: ConvictionBucketStat[];
  }
  export interface DecisionInput {
    run_date: string;            // ISO; ordering key (mirrors Trade.date)
    return_frac: number;         // actual_return as a fraction
    benchmark_frac: number;      // return_frac - alpha  (alpha = return - benchmark)
    conviction: number | null;
    holding_days: number | null;
  }
  export function backtestDecisions(inputs: DecisionInput[]): DecisionTrackRecord
  ```

**Steps:**
- [ ] Read `digiquant/src/digiquant/olympus/atlas/backtest.py` again as the parity reference (helpers `_mean`/`_median`/`_std`/`_downside_std`/`_max_drawdown_pct`/`_compound`/`_bucket_stats`/`backtest_decisions`).
- [ ] Write the failing test `frontend/olympus/lib/decision-track-record.test.ts`. Hard-code three small fixtures and the exact expected outputs computed by hand from the Python formulas:
  ```ts
  import { describe, expect, it } from 'vitest';
  import { backtestDecisions, type DecisionInput } from './decision-track-record';

  const d = (run_date: string, return_frac: number, benchmark_frac: number, conviction: number | null): DecisionInput =>
    ({ run_date, return_frac, benchmark_frac, conviction, holding_days: 10 });

  describe('backtestDecisions (parity with atlas/backtest.py)', () => {
    it('empty → zeroed record', () => {
      const r = backtestDecisions([]);
      expect(r.n_trades).toBe(0);
      expect(r.hit_rate).toBe(0);
      expect(r.information_ratio).toBe(0);
      expect(r.sortino_ratio).toBe(0);
      expect(r.conviction_buckets).toEqual([]);
    });

    it('hit_rate / mean / median alpha in percent points, rounded to 4dp', () => {
      // alphas: +0.04, -0.01, +0.02  → mean 0.0166.., median 0.02
      const r = backtestDecisions([
        d('2026-06-23', 0.05, 0.01, 5),
        d('2026-06-23', 0.00, 0.01, 2),
        d('2026-06-23', 0.03, 0.01, 5),
      ]);
      expect(r.n_trades).toBe(3);
      expect(r.hit_rate).toBe(0.6667); // 2 of 3 positive
      expect(r.mean_alpha_pct).toBe(1.6667);
      expect(r.median_alpha_pct).toBe(2);
    });

    it('information ratio = mean(alpha)/std(alpha) (population std, NOT annualized)', () => {
      // alphas +0.04, -0.01, +0.02; mean 0.016666..; population variance = mean of squared devs
      const r = backtestDecisions([
        d('2026-06-23', 0.05, 0.01, 5),
        d('2026-06-23', 0.00, 0.01, 2),
        d('2026-06-23', 0.03, 0.01, 5),
      ]);
      // std over [0.04,-0.01,0.02] (population): ~0.020683 → IR ~0.8058
      expect(r.information_ratio).toBeCloseTo(0.8058, 3);
    });

    it('sortino falls back to information ratio when no downside (all alpha ≥ 0)', () => {
      const r = backtestDecisions([
        d('2026-06-23', 0.05, 0.01, 5),
        d('2026-06-23', 0.04, 0.01, 4),
      ]);
      expect(r.sortino_ratio).toBe(r.information_ratio);
    });

    it('max drawdown is worst peak-to-trough of the compounded decision returns (negative pct)', () => {
      // returns +0.10 then -0.20 → nav 1.10 then 0.88; dd from peak 1.10 = -20%
      const r = backtestDecisions([
        d('2026-06-23', 0.10, 0.00, 3),
        d('2026-06-24', -0.20, 0.00, 3),
      ]);
      expect(r.max_drawdown_pct).toBeCloseTo(-20, 4);
    });

    it('conviction buckets group by |conviction| (high≥4, medium≥2, low<2), mean alpha pct + n', () => {
      const r = backtestDecisions([
        d('2026-06-23', 0.06, 0.01, 5),  // high, alpha +5%
        d('2026-06-23', 0.04, 0.01, 4),  // high, alpha +3%
        d('2026-06-23', 0.02, 0.01, 2),  // medium, alpha +1%
        d('2026-06-23', 0.00, 0.01, -5), // high (|conv|=5), alpha -1%
      ]);
      const high = r.conviction_buckets.find((b) => b.conviction === 5);
      // emit one bucket entry per present bucket, keyed by a representative conviction:
      // map 'high'→5, 'medium'→3, 'low'→1 (so the chart x-axis is monotone)
      expect(high?.n).toBe(3);
      expect(high?.mean_alpha_pct).toBeCloseTo((5 + 3 - 1) / 3, 4);
    });
  });
  ```
- [ ] Run it, expect FAIL (module missing):
  ```bash
  cd frontend/olympus && npx vitest run lib/decision-track-record.test.ts
  ```
- [ ] Implement `lib/decision-track-record.ts`. Port the helpers verbatim from `backtest.py`. Key parity points: (a) `information_ratio` uses **population** std (divide by `len`, matching `_std`), per-decision, NOT annualized — do **not** reuse `portfolio-risk-metrics.ts`'s `√252` Sharpe; (b) `sortino` falls back to `information_ratio` when downside-std is 0; (c) `max_drawdown_pct` compounds `return_frac` (not alpha) and is rounded to 4dp; (d) bucket thresholds `|conv|≥4 high`, `|conv|≥2 medium`, else `low` (matches `decision-scorecard.ts` `bucketFor`); (e) emit one `ConvictionBucketStat` per present bucket, mapping `high→conviction:5, medium→3, low→1` so the calibration chart x-axis is monotone; (f) round mean/median alpha and hit_rate to 4dp like the Python.
  ```ts
  /**
   * Decision track-record metrics — TS port of digiquant/.../atlas/backtest.py
   * (backtest_decisions). Pure, computed client-side; covered by a parity test.
   * Mirrors the Python exactly: population std for the information ratio (per-decision,
   * NOT annualized — unlike portfolio-risk-metrics.ts's √252 Sharpe), sortino falling
   * back to the info ratio when there is no downside, max drawdown over the compounded
   * decision equity curve. Bucket thresholds match lib/decision-scorecard.ts.
   */
  export interface ConvictionBucketStat {
    conviction: number; // representative: high→5, medium→3, low→1 (monotone x-axis)
    mean_alpha_pct: number;
    n: number;
  }
  export interface DecisionTrackRecord {
    n_trades: number;
    hit_rate: number;
    mean_alpha_pct: number;
    median_alpha_pct: number;
    information_ratio: number;
    sortino_ratio: number;
    max_drawdown_pct: number;
    conviction_buckets: ConvictionBucketStat[];
  }
  export interface DecisionInput {
    run_date: string;
    return_frac: number;
    benchmark_frac: number;
    conviction: number | null;
    holding_days: number | null;
  }

  const HIGH_CONVICTION = 4;
  const MED_CONVICTION = 2;

  function mean(xs: number[]): number {
    return xs.length ? xs.reduce((a, b) => a + b, 0) / xs.length : 0;
  }
  function median(xs: number[]): number {
    if (!xs.length) return 0;
    const s = [...xs].sort((a, b) => a - b);
    const mid = Math.floor(s.length / 2);
    return s.length % 2 ? s[mid] : (s[mid - 1] + s[mid]) / 2;
  }
  function std(xs: number[]): number {
    if (xs.length < 2) return 0;
    const m = mean(xs);
    return Math.sqrt(xs.reduce((s, x) => s + (x - m) ** 2, 0) / xs.length);
  }
  function downsideStd(xs: number[]): number {
    if (xs.length < 2) return 0;
    return Math.sqrt(xs.reduce((s, x) => s + Math.min(0, x) ** 2, 0) / xs.length);
  }
  function maxDrawdownPct(returns: number[]): number {
    let nav = 1;
    let peak = 1;
    let worst = 0;
    for (const r of returns) {
      nav *= 1 + r;
      peak = Math.max(peak, nav);
      if (peak > 0) worst = Math.min(worst, nav / peak - 1);
    }
    return round4(worst * 100);
  }
  function round4(x: number): number {
    return Math.round(x * 1e4) / 1e4;
  }
  type Bucket = 'high' | 'medium' | 'low';
  function bucketFor(conviction: number): Bucket {
    const mag = Math.abs(conviction);
    if (mag >= HIGH_CONVICTION) return 'high';
    if (mag >= MED_CONVICTION) return 'medium';
    return 'low';
  }
  const BUCKET_REP: Record<Bucket, number> = { high: 5, medium: 3, low: 1 };

  function bucketStats(inputs: DecisionInput[]): ConvictionBucketStat[] {
    const order: Bucket[] = ['low', 'medium', 'high'];
    const grouped: Record<Bucket, number[]> = { low: [], medium: [], high: [] };
    for (const t of inputs) {
      if (t.conviction == null) continue;
      grouped[bucketFor(t.conviction)].push(t.return_frac - t.benchmark_frac);
    }
    const out: ConvictionBucketStat[] = [];
    for (const b of order) {
      const alphas = grouped[b];
      if (!alphas.length) continue;
      out.push({ conviction: BUCKET_REP[b], mean_alpha_pct: round4(mean(alphas) * 100), n: alphas.length });
    }
    return out;
  }

  export function backtestDecisions(inputs: DecisionInput[]): DecisionTrackRecord {
    if (!inputs.length) {
      return {
        n_trades: 0, hit_rate: 0, mean_alpha_pct: 0, median_alpha_pct: 0,
        information_ratio: 0, sortino_ratio: 0, max_drawdown_pct: 0, conviction_buckets: [],
      };
    }
    const ordered = [...inputs].sort((a, b) => a.run_date.localeCompare(b.run_date));
    const rets = ordered.map((t) => t.return_frac);
    const alphas = ordered.map((t) => t.return_frac - t.benchmark_frac);
    const stdA = std(alphas);
    const dstdA = downsideStd(alphas);
    const infoRatio = stdA > 0 ? round4(mean(alphas) / stdA) : 0;
    const sortino = dstdA > 0 ? round4(mean(alphas) / dstdA) : infoRatio;
    return {
      n_trades: ordered.length,
      hit_rate: round4(alphas.filter((a) => a > 0).length / alphas.length),
      mean_alpha_pct: round4(mean(alphas) * 100),
      median_alpha_pct: round4(median(alphas) * 100),
      information_ratio: infoRatio,
      sortino_ratio: sortino,
      max_drawdown_pct: maxDrawdownPct(rets),
      conviction_buckets: bucketStats(ordered),
    };
  }
  ```
- [ ] Run the test, expect PASS:
  ```bash
  cd frontend/olympus && npx vitest run lib/decision-track-record.test.ts
  ```
- [ ] Commit:
  ```bash
  git add frontend/olympus/lib/decision-track-record.ts frontend/olympus/lib/decision-track-record.test.ts
  git commit -m "feat(olympus): port backtest.py decision track-record to TS with parity test"
  ```

---

### Task 2: Port the tear-sheet template primitives + `.ts-*` CSS into Olympus

Bring the dependency-free SVG charts (`TimeSeries`, `SignedBars`), the formatters, and the `.ts-*` print/chart CSS into Olympus. No remap is needed: every CSS var the template references (`--up`/`--down`/`--ink`/`--ink-soft`/`--ink-mute`/`--hair`/`--hair-2`/`--surface`/`--surface-2`/`--accent`/`--accent-weak`/`--r-md`/`--r-sm`/`--ease`/`--bg`/`--font-sans`/`--font-mono`) is already declared in `@digithings/design/tokens.css`, which Olympus already imports — and `--accent` there is the cyan `#3DD6C4`, `--up`/`--down` are the fin-green/red. The Olympus `@theme` aliases (`--color-fin-green: var(--up)`, etc.) document the equivalence.

**Files:**
- Create `frontend/olympus/components/tearsheet/charts.tsx` (copy of digiquant-web's, unchanged logic)
- Create `frontend/olympus/components/tearsheet/format.ts` (copy of digiquant-web's, unchanged)
- Create `frontend/olympus/components/tearsheet/types.ts` (see Task 3 — folded here as the file is created here)
- Modify `frontend/olympus/app/globals.css` — append the `.ts-*` CSS block + the `@media print` rules (lines 105-203 of `frontend/digiquant-web/app/globals.css`)

**Interfaces:**
- Consumes: the shared design tokens (already imported).
- Produces: `TimeSeries`, `SignedBars`, `type Scale`, `type Tone` (from `charts.tsx`); `fmtCompact`, `fmtMoney`, `fmtNum`, `fmtPct`, `toneClass` (from `format.ts`).

**Steps:**
- [ ] Copy `frontend/digiquant-web/components/tearsheet/charts.tsx` → `frontend/olympus/components/tearsheet/charts.tsx` verbatim. It imports `./format` and `./types` (created in this + the next task) and is pure SVG (no recharts, no external deps) — safe under static export. Keep the `Empty` component (`msg="no data"`/`"no trades"`); the page passes element-specific messages by gating the chart entirely on the empty-state predicate, so `Empty` is only the inner fallback.
- [ ] Copy `frontend/digiquant-web/components/tearsheet/format.ts` → `frontend/olympus/components/tearsheet/format.ts` verbatim.
- [ ] Append the tear-sheet CSS to `frontend/olympus/app/globals.css`. Copy the `.ts-*` rules and the `@media print` block from `frontend/digiquant-web/app/globals.css` (the contiguous block beginning at the `.ts-status` rule through the closing `}` of `@media print`, i.e. lines ~105-203). Prepend a comment documenting the bridge:
  ```css
  /* ── Performance tear sheet (ported from digiquant-web) ─────────────
     Dependency-free SVG tear sheet. Every var below resolves from the
     shared @digithings/design/tokens.css already imported above:
       --up   ≡ --color-fin-green   --down ≡ --color-fin-red
       --ink  ≡ --color-text-primary --hair ≡ --color-border-subtle
       --accent = cyan #3DD6C4 (chrome/links only — F5 token rule).
     The @media print block makes the page print-to-PDF crisply. */
  ```
  Note: the print block hides `.site-nav`, `.footer`, `.nav-toggle`, `.theme-toggle` — Olympus's chrome uses different class names (`AppFrame`/`Sidebar`). Add Olympus-specific selectors to the print `display:none` list so the sidebar/app-bar don't print. Grep the rendered shell first:
  ```bash
  cd frontend/olympus && grep -nE "className=\"[^\"]*sidebar|aside|app-bar|md:hidden" components/app-frame.tsx components/sidebar.tsx | head
  ```
  Add a `data-print-hide` attribute to the shell wrappers if class names are dynamic, and target `[data-print-hide]` in the print rule — but prefer reusing whatever stable wrapper class the shell already has. Resolve this in the same edit so the printed PDF is just the tear sheet.
- [ ] Run the full suite to confirm nothing broke (CSS + new pure modules don't touch existing tests, but verify):
  ```bash
  cd frontend/olympus && npm test
  ```
  Expect PASS (unchanged count).
- [ ] Commit:
  ```bash
  git add frontend/olympus/components/tearsheet/charts.tsx frontend/olympus/components/tearsheet/format.ts frontend/olympus/app/globals.css
  git commit -m "feat(olympus): port tear-sheet SVG primitives + .ts-* print CSS"
  ```

---

### Task 3: `OlympusTearsheet` types + `fetchOlympusTearsheet()` data builder (+ test)

Define the wrapping type and the fail-soft query that assembles it from `nav_history` + `decision_log` + `portfolio_metrics` + `position_attribution`. The live-NAV track reuses the existing `TearsheetData` shape (`engine='live'`, `strategy='Olympus'`, `symbol='AI-INTELLIGENCE'`); the decision track uses Task 1's `DecisionTrackRecord`. NAV-derived risk ratios reuse `lib/portfolio-risk-metrics.ts` (`computeEffectivePortfolioRiskMetrics`); drawdown is derived in TS mirroring the template's `_drawdown_from_equity`.

**Files:**
- Modify `frontend/olympus/components/tearsheet/types.ts` (created in Task 2) — add `OlympusTearsheet`
- Modify `frontend/olympus/lib/observability-queries.ts` — add `fetchOlympusTearsheet()`
- Test: `frontend/olympus/lib/tearsheet-build.test.ts` (tests the pure assembly helper, mocking the Supabase rows)

**Interfaces:**
- Consumes (Phase 0 + existing):
  - `computeEffectivePortfolioRiskMetrics(serverMetrics, snaps): { sharpe; annVolPct; maxDrawdownPct }` from `lib/portfolio-risk-metrics.ts`
  - `backtestDecisions(inputs: DecisionInput[]): DecisionTrackRecord` from Task 1
  - `TableRow<'nav_history'>` `{ date; nav; cash_pct; invested_pct }`, `TableRow<'decision_log'>` `{ run_date; ticker; stance; conviction; status; actual_return; alpha; holding_days; ... }`, `TableRow<'portfolio_metrics'>`, `TableRow<'position_attribution'>` from `lib/database.types.ts`
  - `TearsheetData` (and `engine: string` — `'live'` is an additive string value, no enum change needed since the field is typed `string`) and `TearsheetPoint` from `frontend/olympus/components/tearsheet/types.ts`
- Produces:
  ```ts
  // components/tearsheet/types.ts
  export interface OlympusTearsheet {
    live: TearsheetData;                 // engine='live', strategy='Olympus', symbol='AI-INTELLIGENCE'
    navPoints: number;                   // nav_history row count (gates the live track)
    decision: DecisionTrackRecord;       // from lib/decision-track-record
    decisionRows: DecisionLogRow[];      // resolved + pending, for the small decision-log table
    nResolved: number;
    nPending: number;
    attribution: TableRow<'position_attribution'>[];  // latest date (absorbed from System)
    attributionDate: string | null;
    inceptionDate: string | null;        // first nav_history.date
    latestNav: number | null;
    generatedAt: string;                 // ISO now
  }
  export interface DecisionLogRow {
    run_date: string; ticker: string; stance: string;
    conviction: number | null; status: string; alpha: number | null; holding_days: number | null;
  }
  // lib/observability-queries.ts
  export function buildOlympusTearsheet(args: {
    nav: TableRow<'nav_history'>[];
    decisions: TableRow<'decision_log'>[];
    metrics: TableRow<'portfolio_metrics'> | null;
    attribution: TableRow<'position_attribution'>[];
    now?: Date;
  }): OlympusTearsheet                   // pure, unit-tested
  export async function fetchOlympusTearsheet(): Promise<OlympusTearsheet>  // fail-soft, calls buildOlympusTearsheet
  ```

**Steps:**
- [ ] Add the `OlympusTearsheet` + `DecisionLogRow` types to `frontend/olympus/components/tearsheet/types.ts` (import `DecisionTrackRecord` from `@/lib/decision-track-record` and `TableRow` from `@/lib/database.types`). Keep the template's `TearsheetData`/`TearsheetPoint`/`TearsheetTrade`/`TearsheetBreakdown` interfaces from the copied file unchanged.
- [ ] Write the failing test `frontend/olympus/lib/tearsheet-build.test.ts` for the pure `buildOlympusTearsheet`:
  ```ts
  import { describe, expect, it } from 'vitest';
  import { buildOlympusTearsheet } from './observability-queries';
  import type { TableRow } from './database.types';

  const navRow = (date: string, nav: number, invested_pct: number | null = 75): TableRow<'nav_history'> =>
    ({ date, nav, cash_pct: invested_pct == null ? null : 100 - invested_pct, invested_pct });

  const dec = (run_date: string, ticker: string, conviction: number | null, status: string, alpha: number | null, actual_return: number | null): TableRow<'decision_log'> =>
    ({ id: `${ticker}-${run_date}`, run_id: 'r1', run_date, ticker, stance: 'buy', conviction, thesis: null,
       benchmark: 'SPY', holding_days: 10, status: status as 'pending' | 'resolved', actual_return, alpha, reflection: null, resolved_at: null, created_at: null });

  describe('buildOlympusTearsheet', () => {
    it('single NAV point → navPoints 1, live track has 1 equity point, no drawdown blow-up', () => {
      const t = buildOlympusTearsheet({ nav: [navRow('2026-06-23', 99.32)], decisions: [], metrics: null, attribution: [], now: new Date('2026-06-24T00:00:00Z') });
      expect(t.navPoints).toBe(1);
      expect(t.live.engine).toBe('live');
      expect(t.live.strategy).toBe('Olympus');
      expect(t.live.symbol).toBe('AI-INTELLIGENCE');
      expect(t.live.equity_curve).toHaveLength(1);
      expect(t.inceptionDate).toBe('2026-06-23');
      expect(t.latestNav).toBe(99.32);
    });

    it('≥2 NAV points → equity + drawdown curves; sharpe from NAV-derived metrics', () => {
      const t = buildOlympusTearsheet({ nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102), navRow('2026-06-25', 101)], decisions: [], metrics: null, attribution: [], now: new Date() });
      expect(t.live.equity_curve).toHaveLength(3);
      expect(t.live.drawdown_curve).toHaveLength(3);
      // drawdown is ≤ 0 everywhere; trough after the 102 peak is (101-102)/102*100 ≈ -0.98
      expect(t.live.drawdown_curve[2].v).toBeCloseTo(-0.9804, 3);
      expect(t.live.max_drawdown_pct).toBeLessThan(0);
    });

    it('decisions split into resolved/pending; track-record from resolved only', () => {
      const t = buildOlympusTearsheet({
        nav: [navRow('2026-06-23', 100)],
        decisions: [
          dec('2026-06-23', 'IJR', 5, 'resolved', 0.04, 0.05),
          dec('2026-06-23', 'EWT', 2, 'resolved', -0.01, 0.0),
          dec('2026-06-23', 'QQQ', 3, 'pending', null, null),
        ],
        metrics: null, attribution: [], now: new Date(),
      });
      expect(t.nResolved).toBe(2);
      expect(t.nPending).toBe(1);
      expect(t.decision.n_trades).toBe(2);     // only resolved feed the track record
      expect(t.decision.hit_rate).toBe(0.5);
      expect(t.decisionRows).toHaveLength(3);   // all rows shown in the small table
    });

    it('prefers persisted portfolio_metrics sharpe over NAV-derived', () => {
      const t = buildOlympusTearsheet({
        nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102)],
        decisions: [], metrics: { id: 'm', date: '2026-06-24', pnl_pct: 2, sharpe: 1.9, volatility: 12, max_drawdown: -3, alpha: 0.5, invested_pct: 75, generated_at: null } as TableRow<'portfolio_metrics'>,
        attribution: [], now: new Date(),
      });
      expect(t.live.sharpe_ratio).toBe(1.9);
    });
  });
  ```
- [ ] Run it, expect FAIL (`buildOlympusTearsheet` missing):
  ```bash
  cd frontend/olympus && npx vitest run lib/tearsheet-build.test.ts
  ```
- [ ] Implement `buildOlympusTearsheet` + `fetchOlympusTearsheet` in `lib/observability-queries.ts`. Add imports at the top: `import { computeEffectivePortfolioRiskMetrics } from './portfolio-risk-metrics'; import { backtestDecisions, type DecisionInput } from './decision-track-record'; import type { OlympusTearsheet, DecisionLogRow } from '@/components/tearsheet/types'; import type { TearsheetData, TearsheetPoint } from '@/components/tearsheet/types';`. Implement the pure builder, then the fetch wrapper reusing the existing `safeSelect` + `latestDateRows` helpers:
  ```ts
  const TEARSHEET_NAV_LIMIT = 2000;

  /** Drawdown (%) from a peak-to-current equity curve — mirrors tearsheet_data._drawdown_from_equity. */
  function drawdownFromEquity(points: TearsheetPoint[]): TearsheetPoint[] {
    if (!points.length) return [];
    let peak = points[0].v;
    return points.map((p) => {
      peak = Math.max(peak, p.v);
      const dd = peak > 0 ? ((p.v - peak) / peak) * 100 : 0;
      return { t: p.t, v: dd };
    });
  }

  export function buildOlympusTearsheet(args: {
    nav: TableRow<'nav_history'>[];
    decisions: TableRow<'decision_log'>[];
    metrics: TableRow<'portfolio_metrics'> | null;
    attribution: TableRow<'position_attribution'>[];
    now?: Date;
  }): OlympusTearsheet {
    const navAsc = [...args.nav].sort((a, b) => a.date.localeCompare(b.date));
    const navPoints = navAsc.length;
    const equity: TearsheetPoint[] = navAsc.map((r) => ({ t: r.date, v: r.nav }));
    const snaps = navAsc.map((r) => ({ date: r.date, nav: r.nav }));
    const drawdown = navPoints >= 2 ? drawdownFromEquity(equity) : [];
    const risk = computeEffectivePortfolioRiskMetrics(
      args.metrics ? { sharpe: args.metrics.sharpe, volatility: args.metrics.volatility, max_drawdown: args.metrics.max_drawdown } : null,
      snaps,
    );
    const inceptionDate = navAsc[0]?.date ?? null;
    const latestNav = navAsc.length ? navAsc[navAsc.length - 1].nav : null;
    const initial = navAsc[0]?.nav ?? 100;
    const final = latestNav ?? initial;

    const live: TearsheetData = {
      schema_version: '1.0',
      strategy: 'Olympus',
      symbol: 'AI-INTELLIGENCE',
      engine: 'live',
      generated_at: (args.now ?? new Date()).toISOString(),
      data_source: 'nav_history',
      period_start: inceptionDate ?? '',
      period_end: navAsc[navAsc.length - 1]?.date ?? '',
      bars: navPoints,
      initial_capital: initial,
      final_equity: final,
      net_profit: final - initial,
      net_profit_pct: initial > 0 ? (final / initial - 1) * 100 : 0,
      max_drawdown_pct: risk.maxDrawdownPct ?? 0,
      sharpe_ratio: risk.sharpe,
      sortino_ratio: null,
      calmar_ratio: null,
      profit_factor: 0,
      win_rate_pct: 0,
      total_trades: 0,        // live track is NAV-level; trade-level fields stay empty (template renders empty-states)
      avg_trade: 0,
      overall: emptyBreakdown(), long: emptyBreakdown(), short: emptyBreakdown(),
      equity_curve: equity,
      drawdown_curve: drawdown,
      trades: [],
      notes: [],
    };

    const resolved = args.decisions.filter((d) => d.status === 'resolved' && d.alpha != null && d.actual_return != null);
    const inputs: DecisionInput[] = resolved.map((d) => ({
      run_date: d.run_date,
      return_frac: d.actual_return as number,
      benchmark_frac: (d.actual_return as number) - (d.alpha as number), // alpha = return − benchmark
      conviction: d.conviction,
      holding_days: d.holding_days,
    }));
    const decision = backtestDecisions(inputs);
    const decisionRows: DecisionLogRow[] = args.decisions.map((d) => ({
      run_date: d.run_date, ticker: d.ticker, stance: d.stance,
      conviction: d.conviction, status: d.status, alpha: d.alpha, holding_days: d.holding_days,
    }));

    return {
      live,
      navPoints,
      decision,
      decisionRows,
      nResolved: resolved.length,
      nPending: args.decisions.filter((d) => d.status === 'pending').length,
      attribution: args.attribution,
      attributionDate: args.attribution.reduce<string | null>((m, r) => (r.date && (m === null || r.date > m) ? r.date : m), null),
      inceptionDate,
      latestNav,
      generatedAt: live.generated_at,
    };
  }

  function emptyBreakdown() {
    return { trades: 0, net_profit: 0, net_profit_pct: 0, gross_profit: 0, gross_loss: 0, percent_profitable: 0, profit_factor: 0, avg_trade: 0, wins: 0, losses: 0 };
  }

  export async function fetchOlympusTearsheet(): Promise<OlympusTearsheet> {
    if (!isSupabaseConfigured() || !supabase) {
      // Configured-but-empty must still render the empty-state tear sheet — return a zeroed build.
      return buildOlympusTearsheet({ nav: [], decisions: [], metrics: null, attribution: [] });
    }
    const [navRes, decisionsRes, metricsRes, attributionRes] = await Promise.all([
      safeSelect<TableRow<'nav_history'>>('nav_history', (sb) =>
        sb.from('nav_history').select('*').order('date', { ascending: true }).limit(TEARSHEET_NAV_LIMIT)),
      safeSelect<TableRow<'decision_log'>>('decision_log', (sb) =>
        sb.from('decision_log').select('id,run_id,run_date,ticker,stance,conviction,thesis,benchmark,holding_days,status,actual_return,alpha,reflection,resolved_at,created_at').order('run_date', { ascending: false }).limit(DECISION_LIMIT)),
      safeSelect<TableRow<'portfolio_metrics'>>('portfolio_metrics', (sb) =>
        sb.from('portfolio_metrics').select('*').order('date', { ascending: false }).limit(1)),
      safeSelect<TableRow<'position_attribution'>>('position_attribution', (sb) =>
        sb.from('position_attribution').select('*').order('date', { ascending: false }).limit(ATTRIBUTION_LIMIT)),
    ]);
    const attribution = latestDateRows(attributionRes.rows);
    return buildOlympusTearsheet({
      nav: navRes.rows,
      decisions: decisionsRes.rows,
      metrics: metricsRes.rows[0] ?? null,
      attribution: attribution.rows,
    });
  }
  ```
- [ ] Run the test, expect PASS:
  ```bash
  cd frontend/olympus && npx vitest run lib/tearsheet-build.test.ts
  ```
- [ ] Commit:
  ```bash
  git add frontend/olympus/components/tearsheet/types.ts frontend/olympus/lib/observability-queries.ts frontend/olympus/lib/tearsheet-build.test.ts
  git commit -m "feat(olympus): OlympusTearsheet type + fetchOlympusTearsheet builder"
  ```

---

### Task 4: The tear-sheet view component (KPI rail + two tracks + Attribution + print)

The presentational surface. One serif H1, one primary KPI strip (NOT a MetricCard wall), then the two `.ts-panel` tracks (live-NAV + decision track-record incl. the two `SignedBars` charts and the conviction-calibration chart), the small decision-log table reusing `.ts-trades`, the absorbed Attribution diagnostics, and a `window.print()` Export button enabled in all states. Each section is independently gated on its empty-state predicate.

**Files:**
- Create `frontend/olympus/components/tearsheet/OlympusTearsheetView.tsx`
- Test: `frontend/olympus/components/tearsheet/OlympusTearsheetView.test.tsx`

**Interfaces:**
- Consumes: `OlympusTearsheet`, `DecisionLogRow` (Task 3); `TimeSeries`, `SignedBars` (Task 2); `fmtCompact`, `fmtMoney`, `fmtNum`, `fmtPct`, `toneClass` (Task 2); `AttributionTab` default export from `@/components/observability/AttributionTab` (absorbed from System); `SignedConvictionBadge` from `@/components/shared/signed-conviction-badge` (F6, Phase 0) for the decision-log table stance.
- Produces: `OlympusTearsheetView({ data }: { data: OlympusTearsheet }): JSX.Element`.

**Steps:**
- [ ] Write the failing test `frontend/olympus/components/tearsheet/OlympusTearsheetView.test.tsx`. Render with `renderToStaticMarkup` (matches `app/page.test.ts`'s SSR-string approach; the SVG charts are deterministic). Assert the empty-state-first behavior and the no-MetricCard-wall hierarchy:
  ```tsx
  import { createElement } from 'react';
  import { renderToStaticMarkup } from 'react-dom/server';
  import { describe, it, expect, vi } from 'vitest';
  import { buildOlympusTearsheet } from '@/lib/observability-queries';
  import { OlympusTearsheetView } from './OlympusTearsheetView';
  import type { TableRow } from '@/lib/database.types';

  vi.mock('@/components/observability/AttributionTab', () => ({ default: () => createElement('div', { 'data-testid': 'attribution' }) }));

  const navRow = (date: string, nav: number): TableRow<'nav_history'> => ({ date, nav, cash_pct: 25, invested_pct: 75 });

  function html(data: Parameters<typeof OlympusTearsheetView>[0]['data']) {
    return renderToStaticMarkup(createElement(OlympusTearsheetView, { data }));
  }

  describe('OlympusTearsheetView', () => {
    it('single NAV point → inception card, not a single-dot chart', () => {
      const data = buildOlympusTearsheet({ nav: [navRow('2026-06-23', 99.32)], decisions: [], metrics: null, attribution: [] });
      const out = html(data);
      expect(out).toContain('Olympus'); // serif H1
      expect(out).toMatch(/live since 2026-06-23/);
      expect(out).toMatch(/equity curve accrues daily/);
      // the live equity TimeSeries must NOT render with 1 point
      expect(out).not.toContain('class="ts-line');
    });

    it('0 resolved decisions → in-flight line, not an empty track-record chart', () => {
      const data = buildOlympusTearsheet({
        nav: [navRow('2026-06-23', 99.32)],
        decisions: [{ id: 'q', run_id: 'r', run_date: '2026-06-23', ticker: 'QQQ', stance: 'buy', conviction: 3, thesis: null, benchmark: 'SPY', holding_days: 10, status: 'pending', actual_return: null, alpha: null, reflection: null, resolved_at: null, created_at: null }],
        metrics: null, attribution: [],
      });
      const out = html(data);
      expect(out).toMatch(/1 decision in flight|decisions in flight/);
      expect(out).toMatch(/track record resolves as holding windows close/);
    });

    it('export button is present in all states', () => {
      const data = buildOlympusTearsheet({ nav: [], decisions: [], metrics: null, attribution: [] });
      expect(html(data)).toMatch(/Download PDF|Export/);
    });

    it('≥2 NAV + resolved decisions → renders the equity line and the calibration chart', () => {
      const data = buildOlympusTearsheet({
        nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102)],
        decisions: [
          { id: 'a', run_id: 'r', run_date: '2026-06-23', ticker: 'IJR', stance: 'buy', conviction: 5, thesis: null, benchmark: 'SPY', holding_days: 10, status: 'resolved', actual_return: 0.05, alpha: 0.04, reflection: null, resolved_at: null, created_at: null },
        ],
        metrics: null, attribution: [],
      });
      const out = html(data);
      expect(out).toContain('ts-line');         // equity curve drawn
      expect(out).toMatch(/Conviction calibration/);
      expect(out).toContain('ts-bar');           // SignedBars rendered
    });
  });
  ```
- [ ] Run it, expect FAIL (component missing):
  ```bash
  cd frontend/olympus && npx vitest run components/tearsheet/OlympusTearsheetView.test.tsx
  ```
- [ ] Implement `OlympusTearsheetView.tsx`. Structure (slop-guarded — one H1, one KPI strip, two labeled `.ts-panel` tracks):
  - Header: `.ts-header` with a serif H1 `Olympus — AI-intelligence strategy` and an eyebrow/meta line `live since {inceptionDate}` + `{navPoints} NAV points · {nResolved} resolved / {nPending} pending`; a `.ts-header-actions` button `Download PDF` calling `window.print()` (always enabled).
  - **Primary KPI strip** (`.ts-kpis`) — a *small* set, not 2×4: `NAV {latestNav} ({net_profit_pct} since inception)` · `Hit rate {decision.hit_rate*100}%` · `Mean alpha {decision.mean_alpha_pct}%` · `Information ratio {decision.information_ratio}`. Each via the `Kpi` mini-component (copy the local `Kpi`/`Toned` from `tearsheet-view.tsx`). Values gated: when `nResolved===0`, the decision KPIs render `—` with a muted sub `in flight`, not fabricated numbers.
  - **Track 1 — Live NAV** (`.ts-panel`, label "Live NAV"): if `navPoints >= 2` render `<TimeSeries points={data.live.equity_curve} scale="linear" tone="accent" fmt={fmtCompact} />` + a drawdown `<TimeSeries points={data.live.drawdown_curve} tone="down" zeroBaseline />`; else the **inception card** — a `.ts-panel` body with `NAV {latestNav ?? 'n/a'} — live since {inceptionDate} — equity curve accrues daily` (no chart). Drop the log/linear/symlog `<select>` (a single track doesn't need it; keep linear).
  - **Track 2 — Decision track record** (`.ts-panel`, label "Decision track record"): if `nResolved >= 1` render (a) a compact KPI sub-rail `Hit rate · Mean alpha · Information ratio · Sortino · Decision max DD · N decisions` from `data.decision`; (b) `<SignedBars values={resolvedAlphasPct} fmt={(v)=>v.toFixed(1)+'%'} />` for per-decision signed alpha (map resolved `decisionRows` `alpha*100`); (c) a **Conviction calibration** sub-panel (heading literal `Conviction calibration`) — `<SignedBars values={data.decision.conviction_buckets.map(b=>b.mean_alpha_pct)} />` with bucket labels (low/medium/high) below; (d) a small decision-log table reusing `.ts-table.ts-trades` (`Run date · Ticker · Stance (SignedConvictionBadge by conviction) · Conviction · Status · Alpha %`). Else the **in-flight line**: `{nPending} decision{nPending===1?'':'s'} in flight — track record resolves as holding windows close` (singular/plural handled).
  - **Attribution diagnostics** (absorbed from System), in its own `.ts-panel` (label "Attribution"): `<AttributionTab attribution={data.attribution} date={data.attributionDate} />`. AttributionTab already renders its own empty state, so no extra gating.
  - **Notes** (`.ts-notes`): `Data source: nav_history + decision_log`, `Generated {generatedAt}`.
  Use the F5 rule: signed alpha/NAV deltas via `toneClass`/`Toned` (fin-green/red); the only cyan is the equity line tone (`tone="accent"`) and the header link/button chrome.
- [ ] Run the test, expect PASS:
  ```bash
  cd frontend/olympus && npx vitest run components/tearsheet/OlympusTearsheetView.test.tsx
  ```
- [ ] Commit:
  ```bash
  git add frontend/olympus/components/tearsheet/OlympusTearsheetView.tsx frontend/olympus/components/tearsheet/OlympusTearsheetView.test.tsx
  git commit -m "feat(olympus): hybrid Performance tear-sheet view (KPI rail + two tracks + attribution)"
  ```

---

### Task 5: Mount the route at `/portfolio/performance` + retire the legacy redirect

Add the real page, wired to `fetchOlympusTearsheet()` client-side (static-export safe), and re-point the old `/performance` redirect at it. The legacy `/performance` page currently redirects to `/portfolio?tab=performance` (a SPA tab being removed); point it at the new route instead.

**Files:**
- Create `frontend/olympus/app/portfolio/performance/page.tsx`
- Modify `frontend/olympus/components/legacy-spa-redirect.tsx` — `PerformanceToPortfolioRedirectPage` now `router.replace('/portfolio/performance')`
- Test: `frontend/olympus/app/portfolio/performance/page.test.ts`

**Interfaces:**
- Consumes: `fetchOlympusTearsheet(): Promise<OlympusTearsheet>` (Task 3), `OlympusTearsheetView` (Task 4), `AtlasLoader`, `SUBPAGE_MAX` (mirror `app/system/page.tsx`).
- Produces: the default-exported `PerformancePage` route component.

**Steps:**
- [ ] Write the failing test `frontend/olympus/app/portfolio/performance/page.test.ts`. Mock `fetchOlympusTearsheet` and assert the loading→loaded transition renders the view, mirroring how `app/system/page.test.ts` exercises a client page (read `app/system/page.test.ts` first for the exact mocking pattern, then mirror it):
  ```ts
  import { describe, it, expect, vi } from 'vitest';
  // mirror app/system/page.test.ts: mock fetchOlympusTearsheet + assert PerformancePage mounts the view
  // (exact harness copied from the system page test to keep the two consistent)
  ```
  (The concrete assertions match `system/page.test.ts`'s structure — load that file in this step and copy its render/await harness verbatim, swapping the mocked fetch + asserting the serif H1 "Olympus" appears after load.)
- [ ] Run it, expect FAIL (route missing):
  ```bash
  cd frontend/olympus && npx vitest run app/portfolio/performance/page.test.ts
  ```
- [ ] Implement `app/portfolio/performance/page.tsx` (client page, mirrors `app/system/page.tsx`):
  ```tsx
  'use client';

  import { useEffect, useState } from 'react';
  import AtlasLoader from '@/components/AtlasLoader';
  import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
  import { OlympusTearsheetView } from '@/components/tearsheet/OlympusTearsheetView';
  import { fetchOlympusTearsheet } from '@/lib/observability-queries';
  import type { OlympusTearsheet } from '@/components/tearsheet/types';

  /**
   * Performance — the hybrid, exportable tear sheet for the single strategy
   * "Olympus": a live-NAV track + an Olympus-specific decision track-record track,
   * each degrading independently, plus the relocated Attribution diagnostics.
   * Empty-state-first; window.print() export enabled in all states.
   */
  export default function PerformancePage() {
    const [data, setData] = useState<OlympusTearsheet | null>(null);
    const [error, setError] = useState<string | null>(null);

    useEffect(() => {
      let alive = true;
      fetchOlympusTearsheet()
        .then((d) => { if (alive) setData(d); })
        .catch((e: unknown) => { if (alive) setError(e instanceof Error ? e.message : 'Failed to load performance data'); });
      return () => { alive = false; };
    }, []);

    return (
      <div className={`${SUBPAGE_MAX} ts-page flex-1 py-4 md:py-6`}>
        {error ? (
          <p className="ts-status ts-status-error">{error}</p>
        ) : !data ? (
          <AtlasLoader fullScreen={false} />
        ) : (
          <OlympusTearsheetView data={data} />
        )}
      </div>
    );
  }
  ```
  (`fetchOlympusTearsheet` is fail-soft and never throws on empty/RLS-deny — the empty-state tear sheet renders, so `error` is reserved for genuine misconfiguration if `fetchOlympusTearsheet` is later hardened to throw; today it returns a zeroed build.)
- [ ] Re-point the legacy redirect. Edit `frontend/olympus/components/legacy-spa-redirect.tsx`:
  ```tsx
  // PerformanceToPortfolioRedirectPage
      router.replace('/portfolio/performance');
  ```
  (The standalone `/performance` route — `app/performance/page.tsx` — already re-exports `PerformanceToPortfolioRedirectPage`, so the old URL now lands on the real tear sheet.)
- [ ] Run both the new page test and the redirect's existing test, expect PASS:
  ```bash
  cd frontend/olympus && npx vitest run app/portfolio/performance/page.test.ts components/legacy-spa-redirect.test.tsx 2>/dev/null; npx vitest run app/portfolio/performance/page.test.ts
  ```
  (If a `legacy-spa-redirect.test.tsx` exists and asserts the old `/portfolio?tab=performance` target, update that assertion to `/portfolio/performance` in this same step.)
- [ ] Run the full suite, expect all green:
  ```bash
  cd frontend/olympus && npm test
  ```
- [ ] Commit:
  ```bash
  git add frontend/olympus/app/portfolio/performance/page.tsx frontend/olympus/app/portfolio/performance/page.test.ts frontend/olympus/components/legacy-spa-redirect.tsx
  git commit -m "feat(olympus): mount /portfolio/performance tear-sheet route, re-point legacy /performance"
  ```

---

### Task 6: Cross-link entry from Portfolio + verification sweep

Make the tear sheet discoverable (a "Performance" entry ramp from the Portfolio surface) and run the final verification per the F5/empty-state constraints. This task is small and folds in the documentation + lint check.

**Files:**
- Modify `frontend/olympus/components/portfolio/PortfolioShellInner.tsx` (or the Portfolio sub-nav source — confirm by grep) — add a "Performance" link to `/portfolio/performance`
- Modify `frontend/olympus/components/portfolio/ARCHITECTURE.md` *(only if it exists — per CLAUDE.md, update ARCHITECTURE after an interface change; otherwise skip)*

**Interfaces:**
- Consumes: the locked deep-link grammar is NOT used here (Performance is a single strategy page, not a Pipeline node); the link is a plain `/portfolio/performance` route. Contextual-link slop guard: this is a real new destination, not a cloned "View in Pipeline" button.
- Produces: nothing other surfaces consume.

**Steps:**
- [ ] Find the Portfolio sub-navigation source:
  ```bash
  cd frontend/olympus && grep -rn "tab=theses\|tab=performance\|Holdings\|Theses\|subpage-tab-bar\|portfolio/theses" components/portfolio/PortfolioShellInner.tsx components/subpage-tab-bar.tsx | head
  ```
- [ ] Add a "Performance" entry pointing at `/portfolio/performance` alongside the existing Holdings/Theses tabs (match the existing tab-item JSX/styling exactly — read the file's tab list first, then add one item; if tabs are query-param driven within `/portfolio`, instead add a sibling link styled as the others that navigates to the dedicated route).
- [ ] If `frontend/olympus/components/portfolio/ARCHITECTURE.md` exists, add one line under its route/surface map: `/portfolio/performance — hybrid tear sheet (live-NAV + decision track record), OlympusTearsheetView ← fetchOlympusTearsheet`.
- [ ] Lint the changed TS (follow repo eslint/prettier; ruff is Python-only and does not apply):
  ```bash
  cd frontend/olympus && npx eslint components/tearsheet app/portfolio/performance lib/decision-track-record.ts --max-warnings=0 && npx prettier --check "components/tearsheet/**" "app/portfolio/performance/**" "lib/decision-track-record.ts" "lib/observability-queries.ts"
  ```
  Fix any reported issue (run `npx prettier --write` on the listed paths if formatting drifts).
- [ ] Run the full suite one final time, expect all green (no regressions in the 150+ plumbing/page tests):
  ```bash
  cd frontend/olympus && npm test
  ```
- [ ] Commit:
  ```bash
  git add frontend/olympus/components/portfolio
  git commit -m "feat(olympus): link Performance tear sheet from Portfolio sub-nav"
  ```

---

## Notes for the executor

- **D2 backtest-seed gates the populated demo.** Until the `nav_history` (≥2 points) + resolved `decision_log` batch is seeded upstream, this surface correctly shows the inception card + "decisions in flight" line. That is the honest default, not a bug. The backend seed is **issue #2 in the spec's Phase-0 backend list** — reference it as `Fixes #<N>` (file it if not yet filed) on whichever commit you want auto-linked, or use a `task/<N>-slug` branch.
- **`engine: 'live'` is additive without an enum change** — `TearsheetData.engine` is typed `string` in the copied `types.ts`, so `'live'` is a valid value; no edit to the template's type is required.
- **The decision track record uses RESOLVED rows only** (`status==='resolved' && alpha != null`), while the small decision-log table shows all rows (resolved + pending) so the in-flight decisions are visible. The KPI rail's decision KPIs render `—` when `nResolved===0`.
- **Attribution is absorbed here** by mounting the existing `AttributionTab` unchanged. The System surface's own Phase-1 work removes Attribution from System; this plan only *adds* the consumer — coordinate so both land before the System redesign claims Attribution is gone.
- **No recharts in the tear sheet** — the ported `TimeSeries`/`SignedBars` are pure SVG, which is required for crisp print-to-PDF and keeps the page light. Do not swap them for recharts.
