'use client';

import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
  DivergingBars,
  EmptyState,
  WaterfallBridge,
} from '@digithings/ui/ui';
import {
  bridgeSteps,
  buildBookAttribution,
  signedPct,
  type BookAttributionView,
} from '@/lib/portfolio-performance-view';
import type { TableRow } from '@/lib/database.types';

type AttributionRow = TableRow<'position_attribution'>;

const pct = (n: number) => signedPct(n);

function bridgeSummary(view: BookAttributionView): string | null {
  const b = view.bridge;
  if (!b) return null;
  return (
    `Benchmark ${pct(b.benchmarkPct)}, selection ${pct(b.selectionPct)}, ` +
    `cash allocation ${pct(b.allocationPct)}` +
    (Math.abs(b.residualPct) >= 0.005 ? `, residual ${pct(b.residualPct)}` : '') +
    `, portfolio ${pct(b.portfolioPct)} over the current-book lookback.`
  );
}

/**
 * Current-book lookback attribution: benchmark -> selection -> cash allocation
 * -> portfolio bridge, plus ranked per-holding contribution and selection bars.
 * A diagnostic of TODAY's weights over a trailing window, never realized P&L.
 */
export function BookAttribution({ rows }: { rows: readonly AttributionRow[] }) {
  const view = buildBookAttribution(rows);

  if (!view) {
    return (
      <section data-testid="book-attribution" aria-label="Current-book lookback attribution">
        <EmptyState title="No current-book lookback rows yet" />
      </section>
    );
  }

  const summary = bridgeSummary(view);
  const window = rows.find((r) => r.window_start_date && r.window_end_date);

  return (
    <section
      data-testid="book-attribution"
      aria-label="Current-book lookback attribution"
      className="flex flex-col gap-4 border border-hair bg-surface p-4"
    >
      <header className="flex flex-wrap items-baseline justify-between gap-2">
        <h2 className="font-display text-xl font-normal text-ink">Where the excess came from</h2>
        <span
          data-testid="book-attribution-label"
          className="font-mono text-[0.62rem] uppercase tracking-wider text-ink-mute"
        >
          Current-book lookback diagnostic - not realized daily contribution
          {window ? ` · ${window.window_start_date} to ${window.window_end_date}` : ''}
        </span>
      </header>

      {view.unpriced > 0 ? (
        <p data-testid="book-attribution-unpriced" className="m-0 font-mono text-xs text-warn">
          {view.unpriced} of {view.holdings} holdings have no priced lookback window; totals
          under-count their effect.
        </p>
      ) : null}

      {view.bridge ? (
        <div data-testid="attribution-bridge">
          <WaterfallBridge
            steps={bridgeSteps(view.bridge)}
            formatValue={pct}
            label="Benchmark to portfolio return bridge"
          />
          {summary ? <p className="sr-only">{summary}</p> : null}
        </div>
      ) : (
        <p className="m-0 font-mono text-xs text-ink-mute">
          No benchmark return stored for this window, so the bridge cannot be anchored. Active
          return (selection + allocation): {pct(view.activePct)}.
        </p>
      )}

      <div className="grid gap-6 md:grid-cols-2">
        <div>
          <h3 className="m-0 mb-2 font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute">
            Contribution (weight × return)
          </h3>
          <DivergingBars
            items={view.contributors.map((b) => ({
              id: b.id,
              label: b.label,
              value: b.value,
              display: pct(b.value),
            }))}
            sort="abs"
            label="Per-holding contribution, percentage points"
          />
        </div>
        <div>
          <h3 className="m-0 mb-2 font-mono text-[0.65rem] uppercase tracking-wider text-ink-mute">
            Selection (weight × excess vs benchmark)
          </h3>
          <DivergingBars
            items={view.selectors.map((b) => ({
              id: b.id,
              label: b.label,
              value: b.value,
              display: pct(b.value),
            }))}
            sort="abs"
            label="Per-holding selection effect, percentage points"
          />
        </div>
      </div>

      <Collapsible>
        <CollapsibleTrigger className="font-mono text-[0.65rem] uppercase tracking-wider text-accent hover:underline">
          Decomposition table
        </CollapsibleTrigger>
        <CollapsibleContent>
          <table className="mt-2 w-full border-collapse font-mono text-[0.75rem] tabular-nums">
            <thead>
              <tr className="text-left text-[0.58rem] uppercase tracking-wider text-ink-mute">
                <th className="py-1 font-normal">Holding</th>
                <th className="py-1 text-right font-normal">Weight</th>
                <th className="py-1 text-right font-normal">Return</th>
                <th className="py-1 text-right font-normal">Contrib.</th>
                <th className="py-1 text-right font-normal">Selection</th>
                <th className="py-1 text-right font-normal">Allocation</th>
              </tr>
            </thead>
            <tbody>
              {rows.map((r) => (
                <tr key={r.id} className="border-t border-hair">
                  <td className="py-1 text-ink">{r.ticker}</td>
                  <td className="py-1 text-right text-ink-soft">
                    {r.weight_pct == null ? '—' : `${r.weight_pct.toFixed(1)}%`}
                  </td>
                  <td className="py-1 text-right text-ink-soft">
                    {r.position_return_pct == null ? '—' : pct(r.position_return_pct)}
                  </td>
                  <td className="py-1 text-right">{r.contribution_pct == null ? '—' : pct(r.contribution_pct)}</td>
                  <td className="py-1 text-right">
                    {r.selection_effect_pct == null ? '—' : pct(r.selection_effect_pct)}
                  </td>
                  <td className="py-1 text-right">
                    {r.allocation_effect_pct == null ? '—' : pct(r.allocation_effect_pct)}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </CollapsibleContent>
      </Collapsible>
    </section>
  );
}
