'use client';

import type { ServerPortfolioMetrics } from '@/lib/types';
import type { EffectivePortfolioRiskMetrics } from '@/lib/portfolio-risk-metrics';

export function ServerMetricsStrip({
  m,
  effectiveRisk,
}: {
  m: ServerPortfolioMetrics;
  effectiveRisk: EffectivePortfolioRiskMetrics;
}) {
  return (
    <div className="px-6 py-4 border-b border-hair bg-term-bg/80">
      <p className="text-[11px] text-ink-mute mb-2">
        Server metrics
        {m.as_of_date || m.date ? ` · ${m.as_of_date ?? m.date}` : ''}
        {m.generated_at ? ` · ${m.generated_at.slice(0, 19)}` : ''}
      </p>
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <span className="text-ink-soft">
          P&amp;L:{' '}
          <span className={`qn-metric ${m.pnl_pct != null ? (m.pnl_pct >= 0 ? 'qn-up' : 'qn-down') : 'text-ink'}`}>
            {m.pnl_pct != null ? `${m.pnl_pct >= 0 ? '+' : ''}${m.pnl_pct.toFixed(2)}%` : '—'}
          </span>
        </span>
        <span className="text-ink-soft">
          Sharpe:{' '}
          <span className="qn-metric text-ink">
            {effectiveRisk.sharpe != null ? effectiveRisk.sharpe.toFixed(2) : '—'}
          </span>
        </span>
        <span className="text-ink-soft">
          Vol:{' '}
          <span className="qn-metric text-ink">
            {effectiveRisk.annVolPct != null ? `${effectiveRisk.annVolPct.toFixed(2)}%` : '—'}
          </span>
        </span>
        <span className="text-ink-soft">
          Max DD:{' '}
          <span className={`qn-metric ${effectiveRisk.maxDrawdownPct != null && effectiveRisk.maxDrawdownPct < 0 ? 'qn-down' : 'text-ink'}`}>
            {effectiveRisk.maxDrawdownPct != null ? `${effectiveRisk.maxDrawdownPct.toFixed(2)}%` : '—'}
          </span>
        </span>
        <span className="text-ink-soft">
          Cash:{' '}
          <span className="qn-metric text-ink">
            {m.cash_pct != null ? `${m.cash_pct.toFixed(1)}%` : '—'}
          </span>
        </span>
        <span className="text-ink-soft">
          Invested:{' '}
          <span className="qn-metric text-ink">
            {m.invested_pct != null ? `${m.invested_pct.toFixed(1)}%` : '—'}
          </span>
        </span>
      </div>
    </div>
  );
}
