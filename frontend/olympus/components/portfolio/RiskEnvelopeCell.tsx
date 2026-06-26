'use client';

/**
 * Advisory risk envelope (relocated from System's PositionRiskTab). stop_loss_pct is a
 * downside %, target_pct_gain an upside % gain, horizon_days the holding window. These are
 * display-only — NOT orders, never sent to any broker (the book is paper-only).
 */
export default function RiskEnvelopeCell({
  stopLossPct,
  targetPctGain,
  horizonDays,
}: {
  stopLossPct: number | null | undefined;
  targetPctGain: number | null | undefined;
  horizonDays: number | null | undefined;
}) {
  const hasStop = stopLossPct != null;
  const hasTarget = targetPctGain != null;
  const hasHorizon = horizonDays != null;
  if (!hasStop && !hasTarget && !hasHorizon) {
    return <span className="text-text-muted">—</span>;
  }
  // Position the entry (0%) tick proportionally between the stop and target ends.
  const down = hasStop ? Math.abs(stopLossPct as number) : 0;
  const up = hasTarget ? Math.abs(targetPctGain as number) : 0;
  const span = down + up;
  const entryPct = span > 0 ? (down / span) * 100 : 50;
  return (
    <div className="flex items-center justify-end gap-2">
      <div className="flex flex-col items-end gap-1">
        <div className="flex items-center gap-2 font-mono text-[11px] tabular-nums">
          <span className={hasStop ? 'text-fin-red' : 'text-text-muted'}>
            {hasStop
              ? `${(stopLossPct as number) >= 0 ? '+' : ''}${(stopLossPct as number).toFixed(1)}%`
              : '—'}
          </span>
          <span className="text-text-muted">↔</span>
          <span className={hasTarget ? 'text-fin-green' : 'text-text-muted'}>
            {hasTarget ? `+${(targetPctGain as number).toFixed(1)}%` : '—'}
          </span>
        </div>
        {(hasStop || hasTarget) && (
          <div className="relative h-1 w-24 rounded-full bg-bg-secondary">
            <div className="absolute inset-y-0 left-0 w-1/2 rounded-l-full bg-fin-red/40" />
            <div className="absolute inset-y-0 right-0 w-1/2 rounded-r-full bg-fin-green/40" />
            <div
              className="absolute -top-0.5 h-2 w-0.5 bg-[var(--accent)]"
              style={{ left: `${entryPct}%` }}
              aria-hidden
            />
          </div>
        )}
      </div>
      {hasHorizon && (
        <span className="rounded border border-fin-amber/30 bg-fin-amber/10 px-1.5 py-0.5 font-mono text-[10px] tabular-nums text-fin-amber">
          {horizonDays}d
        </span>
      )}
    </div>
  );
}
