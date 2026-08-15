'use client';

import { SafeMarkdown } from '@/components/SafeMarkdown';
import { cleanMemoProse, summarizeRecommendedPortfolio } from '@/lib/render-pipeline-payloads';

// Legacy shape: body.rebalance_table rows
type LegacyRow = {
  ticker?: string;
  current_pct?: number | null;
  recommended_pct?: number | null;
  change_pct?: number | null;
  action?: string;
  urgency?: string;
  rationale?: string;
};

// Live automated shape: payload.actions rows
// `target_pct` is the canonical live-shape field; `recommended_pct` is used by
// fixtures and test payloads — both are accepted so the UI renders either shape.
type ActionRow = {
  ticker?: string;
  action?: string; // hold | add | trim | exit | new
  current_pct?: number | null;
  target_pct?: number | null;
  recommended_pct?: number | null; // fixture / test alias for target_pct
  rationale?: string;
};

// Live automated shape: payload.recommended_portfolio rows
// `target_pct` is the canonical live-shape field; `weight_pct` is used by
// fixtures and test payloads — both are accepted so the UI renders either shape.
type WeightRow = {
  ticker?: string;
  target_pct?: number | null;
  weight_pct?: number | null; // fixture / test alias for target_pct
};

function pct(n: unknown): string {
  if (n == null || Number.isNaN(Number(n))) return '—';
  return `${Number(n).toFixed(2)}%`;
}

/** Badge colour keyed on action verb (live shape) */
function actionClass(action: string | undefined): string {
  switch (action) {
    case 'add':
    case 'new':
      return 'text-up';
    case 'trim':
    case 'exit':
      return 'text-down/90';
    default:
      return 'text-ink-soft';
  }
}

export default function RebalanceDocumentView({
  payload,
  fallbackMarkdown,
}: {
  payload: Record<string, unknown> | null;
  fallbackMarkdown: string;
}) {
  // ── Live automated shape ─────────────────────────────────────────────────
  // { recommended_portfolio: [{ticker, target_pct}], actions: [{ticker, action,
  //   current_pct, target_pct, rationale}], notes: string }
  const liveActions: ActionRow[] = Array.isArray(payload?.actions)
    ? (payload.actions as ActionRow[])
    : [];
  const liveWeights: WeightRow[] = Array.isArray(payload?.recommended_portfolio)
    ? (payload.recommended_portfolio as WeightRow[])
    : [];
  const liveNotes =
    payload?.notes != null && typeof payload.notes === 'string' && payload.notes.trim()
      ? payload.notes.trim()
      : '';
  const liveSummary = summarizeRecommendedPortfolio(payload);

  const isLiveShape = liveActions.length > 0 || liveWeights.length > 0 || liveNotes !== '';

  // ── Legacy shape ─────────────────────────────────────────────────────────
  // { body: { rebalance_table: [...], pm_notes, delta_summary } }
  const body =
    payload && typeof payload.body === 'object' && payload.body !== null && !Array.isArray(payload.body)
      ? (payload.body as Record<string, unknown>)
      : null;
  const table = body?.rebalance_table;
  const legacyRows: LegacyRow[] = Array.isArray(table) ? (table as LegacyRow[]) : [];
  const pmNotes = body?.pm_notes != null ? String(body.pm_notes) : '';
  const deltaSummary = body?.delta_summary;
  const ds =
    deltaSummary && typeof deltaSummary === 'object' && !Array.isArray(deltaSummary)
      ? (deltaSummary as Record<string, unknown>)
      : null;

  // ── Fallback ─────────────────────────────────────────────────────────────
  if (!isLiveShape && !legacyRows.length && !pmNotes) {
    return (
      <SafeMarkdown>{fallbackMarkdown}</SafeMarkdown>
    );
  }

  // ── Live automated shape rendering ───────────────────────────────────────
  if (isLiveShape) {
    return (
      <div className="space-y-6 text-sm">
        {liveSummary ? (
          <div className="rounded-lg border border-accent/15 bg-accent/[0.04] p-4">
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-3">
              Post-risk-sizing book summary
            </h3>
            <div className="grid grid-cols-3 gap-3 text-xs">
              <div>
                <p className="text-[10px] uppercase tracking-wider text-ink-mute">Invested</p>
                <p className="text-base font-semibold tabular-nums text-ink">
                  {liveSummary.investedPct.toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-ink-mute">Cash</p>
                <p className="text-base font-semibold tabular-nums text-ink">
                  {liveSummary.cashPct.toFixed(2)}%
                </p>
              </div>
              <div>
                <p className="text-[10px] uppercase tracking-wider text-ink-mute">Holdings</p>
                <p className="text-base font-semibold tabular-nums text-ink">
                  {liveSummary.holdingsCount}
                </p>
              </div>
            </div>
            <p className="mt-3 text-[11px] text-ink-mute leading-relaxed">
              Structured recommended weights are the source of truth if narrative notes conflict.
            </p>
          </div>
        ) : null}
        {liveNotes ? (
          <div>
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
              Narrative / memo notes
            </h3>
            <SafeMarkdown>{cleanMemoProse(liveNotes)}</SafeMarkdown>
          </div>
        ) : null}

        {liveWeights.length > 0 ? (
          <div className="overflow-x-auto">
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
              Recommended weights
            </h3>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-hair text-ink-mute">
                  <th className="py-2 pr-3 font-medium">Ticker</th>
                  <th className="py-2 font-medium text-right">Target %</th>
                </tr>
              </thead>
              <tbody>
                {liveWeights.map((w, i) => (
                  <tr key={i} className="border-b border-hair/60">
                    <td className="py-2 pr-3 font-mono text-accent">{w.ticker ?? '—'}</td>
                    {/* Live shape: `target_pct`; fixture / test payloads: `weight_pct`. */}
                    <td className="py-2 text-right tabular-nums">{pct(w.target_pct ?? w.weight_pct)}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}

        {liveActions.length > 0 ? (
          <div className="overflow-x-auto">
            <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Actions</h3>
            <table className="w-full text-left text-xs border-collapse">
              <thead>
                <tr className="border-b border-hair text-ink-mute">
                  <th className="py-2 pr-3 font-medium">Ticker</th>
                  <th className="py-2 pr-3 font-medium">Action</th>
                  <th className="py-2 pr-3 font-medium text-right">Current</th>
                  <th className="py-2 pr-3 font-medium text-right">Target</th>
                  <th className="py-2 font-medium">Rationale</th>
                </tr>
              </thead>
              <tbody>
                {liveActions.map((a, i) => (
                  <tr key={i} className="border-b border-hair/60 align-top">
                    <td className="py-2 pr-3 font-mono text-accent">{a.ticker ?? '—'}</td>
                    <td className={`py-2 pr-3 font-medium ${actionClass(a.action)}`}>{a.action ?? '—'}</td>
                    <td className="py-2 pr-3 text-right tabular-nums">{pct(a.current_pct)}</td>
                    {/* Live shape: `target_pct`; fixture / test payloads: `recommended_pct`. */}
                    <td className="py-2 pr-3 text-right tabular-nums">{pct(a.target_pct ?? a.recommended_pct)}</td>
                    <td className="py-2 text-ink-soft whitespace-pre-wrap">
                      {cleanMemoProse(a.rationale ?? '—')}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        ) : null}
      </div>
    );
  }

  // ── Legacy shape rendering ────────────────────────────────────────────────
  return (
    <div className="space-y-6 text-sm">
      {ds && (
        <div className="rounded-lg border border-hair bg-term-bg/50 p-4 space-y-1 text-ink-soft">
          <p className="text-xs font-semibold text-ink-mute uppercase tracking-wider">Delta summary</p>
          <p>
            Changes triggered: <span className="text-ink">{String(ds.changes_triggered ?? '—')}</span> · Held:{' '}
            <span className="text-ink">{String(ds.held_count ?? '—')}</span>
          </p>
          {ds.largest_move != null && String(ds.largest_move).trim() ? (
            <p>
              Largest move: <span className="text-ink">{String(ds.largest_move)}</span>
            </p>
          ) : null}
          {Array.isArray(ds.new_entries) && ds.new_entries.length > 0 ? (
            <p>
              New: <span className="text-accent">{ds.new_entries.join(', ')}</span>
            </p>
          ) : null}
          {Array.isArray(ds.exits) && ds.exits.length > 0 ? (
            <p>
              Exits: <span className="text-down/90">{ds.exits.join(', ')}</span>
            </p>
          ) : null}
        </div>
      )}

      {pmNotes ? (
        <div>
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">
            Narrative / memo notes
          </h3>
          <SafeMarkdown>{cleanMemoProse(pmNotes)}</SafeMarkdown>
        </div>
      ) : null}

      {legacyRows.length > 0 ? (
        <div className="overflow-x-auto">
          <h3 className="text-xs font-semibold text-ink-mute uppercase tracking-wider mb-2">Rebalance table</h3>
          <table className="w-full text-left text-xs border-collapse">
            <thead>
              <tr className="border-b border-hair text-ink-mute">
                <th className="py-2 pr-3 font-medium">Ticker</th>
                <th className="py-2 pr-3 font-medium text-right">Current</th>
                <th className="py-2 pr-3 font-medium text-right">Target</th>
                <th className="py-2 pr-3 font-medium text-right">Δ</th>
                <th className="py-2 pr-3 font-medium">Action</th>
                <th className="py-2 pr-3 font-medium">Urgency</th>
                <th className="py-2 font-medium">Rationale</th>
              </tr>
            </thead>
            <tbody>
              {legacyRows.map((r, i) => (
                <tr key={i} className="border-b border-hair/60 align-top">
                  <td className="py-2 pr-3 font-mono text-accent">{r.ticker ?? '—'}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.current_pct)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.recommended_pct)}</td>
                  <td className="py-2 pr-3 text-right tabular-nums">{pct(r.change_pct)}</td>
                  <td className="py-2 pr-3">{r.action ?? '—'}</td>
                  <td className="py-2 pr-3">{r.urgency ?? '—'}</td>
                  <td className="py-2 text-ink-soft whitespace-pre-wrap">
                    {cleanMemoProse(r.rationale ?? '—')}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      ) : null}
    </div>
  );
}
