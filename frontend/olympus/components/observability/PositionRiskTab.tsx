'use client';

import { useMemo } from 'react';
import type { TableRow } from '@/lib/database.types';
import { EmptyState, SectionCard, StatTile, fmtNum, fmtPct, signColorClass } from './shared';

const RISK_KEYS = ['stop_loss_pct', 'target_pct_gain', 'horizon_days', 'conviction'] as const;

function hasAnyRiskField(p: TableRow<'positions'>): boolean {
  return RISK_KEYS.some((k) => p[k] != null);
}

export default function PositionRiskTab({
  positions,
  date,
}: {
  positions: TableRow<'positions'>[];
  date: string | null;
}) {
  const holdings = useMemo(
    () => positions.filter((p) => p.ticker !== 'CASH'),
    [positions]
  );
  const riskPopulated = useMemo(() => holdings.some(hasAnyRiskField), [holdings]);

  if (!holdings.length) {
    return (
      <EmptyState
        title="No holdings to show"
        message="The paper book currently holds no non-cash positions, so there are no per-position risk fields to display."
      />
    );
  }

  if (!riskPopulated) {
    return (
      <EmptyState
        title="Advisory risk fields not populated"
        message="Per-position stops, targets, horizons, and conviction are written when the OLYMPUS_POSITION_RISK_FIELDS flag is enabled (migration 039). The book holds positions, but these advisory fields are not yet populated."
        note="Advisory stop/target/conviction fields appear once per-position risk fields are enabled (OLYMPUS_POSITION_RISK_FIELDS)."
      />
    );
  }

  const convictionVals = holdings.filter((p) => p.conviction != null).map((p) => p.conviction ?? 0);
  // null (not 0) when no holding carries a conviction, so we render "—" rather than a false 0.00.
  const avgConviction = convictionVals.length
    ? convictionVals.reduce((a, c) => a + c, 0) / convictionVals.length
    : null;
  const withStops = holdings.filter((p) => p.stop_loss_pct != null).length;
  const withTargets = holdings.filter((p) => p.target_pct_gain != null).length;

  return (
    <div className="flex flex-col gap-6">
      <div className="grid grid-cols-2 gap-3 lg:grid-cols-4">
        <StatTile label="As of" value={date ?? '—'} sub={`${holdings.length} holdings`} />
        <StatTile
          label="Avg conviction"
          value={avgConviction != null ? avgConviction.toFixed(2) : '—'}
          sub="−5 to +5 scale"
        />
        <StatTile label="With stop-loss" value={`${withStops}/${holdings.length}`} />
        <StatTile label="With target" value={`${withTargets}/${holdings.length}`} />
      </div>

      <SectionCard
        title="Per-position risk"
        subtitle="Advisory display fields derived from ATR + conviction — NOT orders and not sent to any broker. The book is paper-only."
      >
        <div className="overflow-x-auto">
          <table className="w-full text-sm tabular-nums">
            <thead>
              <tr className="text-left text-xs text-text-muted border-b border-border-subtle">
                <th className="py-2 pr-4 font-medium">Ticker</th>
                <th className="py-2 pr-4 font-medium">Sector</th>
                <th className="py-2 pr-4 font-medium text-right">Weight</th>
                <th className="py-2 pr-4 font-medium text-right">Conviction</th>
                <th className="py-2 pr-4 font-medium text-right">Entry</th>
                <th className="py-2 pr-4 font-medium text-right">Stop-loss</th>
                <th className="py-2 pr-4 font-medium text-right">Target</th>
                <th className="py-2 font-medium text-right">Horizon</th>
              </tr>
            </thead>
            <tbody>
              {holdings.map((p) => (
                <tr key={p.id} className="border-b border-border-subtle/50">
                  <td className="py-2 pr-4 text-text-primary">{p.ticker}</td>
                  <td className="py-2 pr-4 text-text-muted truncate max-w-[160px]">
                    {p.sector_bucket ?? p.category ?? '—'}
                  </td>
                  <td className="py-2 pr-4 text-right text-text-secondary">{fmtPct(p.weight_pct, 1)}</td>
                  <td className="py-2 pr-4 text-right text-text-secondary">
                    {p.conviction != null ? p.conviction.toFixed(1) : '—'}
                  </td>
                  <td className="py-2 pr-4 text-right text-text-secondary">
                    {p.entry_price != null ? p.entry_price.toFixed(2) : '—'}
                  </td>
                  <td className={`py-2 pr-4 text-right ${p.stop_loss_pct != null ? 'text-fin-red' : 'text-text-muted'}`}>
                    {fmtPct(p.stop_loss_pct, 1)}
                  </td>
                  <td className={`py-2 pr-4 text-right ${p.target_pct_gain != null ? 'text-fin-green' : 'text-text-muted'}`}>
                    {fmtPct(p.target_pct_gain, 1)}
                  </td>
                  <td className="py-2 text-right text-text-secondary">
                    {p.horizon_days != null ? `${fmtNum(p.horizon_days)}d` : '—'}
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </SectionCard>
    </div>
  );
}
