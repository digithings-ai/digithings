'use client';

import type { ServerPortfolioMetrics } from '@/lib/types';

export function ServerMetricsStrip({ m }: { m: ServerPortfolioMetrics }) {
  return (
    <div className="px-6 py-4 border-b border-border-subtle bg-bg-secondary/80">
      <p className="text-[11px] text-text-muted mb-2">
        Server metrics
        {m.as_of_date || m.date ? ` · ${m.as_of_date ?? m.date}` : ''}
        {m.generated_at ? ` · ${m.generated_at.slice(0, 19)}` : ''}
      </p>
      <div className="flex flex-wrap gap-x-6 gap-y-2 text-sm">
        <span className="text-text-secondary">
          P&amp;L:{' '}
          <span className="text-text-primary font-mono tabular-nums">
            {m.pnl_pct != null ? `${m.pnl_pct >= 0 ? '+' : ''}${m.pnl_pct.toFixed(2)}%` : '—'}
          </span>
        </span>
        <span className="text-text-secondary">
          Sharpe:{' '}
          <span className="text-text-primary font-mono tabular-nums">
            {m.sharpe != null ? m.sharpe.toFixed(2) : '—'}
          </span>
        </span>
        <span className="text-text-secondary">
          Vol:{' '}
          <span className="text-text-primary font-mono tabular-nums">
            {m.volatility != null ? `${m.volatility.toFixed(2)}%` : '—'}
          </span>
        </span>
        <span className="text-text-secondary">
          Max DD:{' '}
          <span className="text-text-primary font-mono tabular-nums">
            {m.max_drawdown != null ? `${m.max_drawdown.toFixed(2)}%` : '—'}
          </span>
        </span>
        <span className="text-text-secondary">
          Cash:{' '}
          <span className="text-text-primary font-mono tabular-nums">
            {m.cash_pct != null ? `${m.cash_pct.toFixed(1)}%` : '—'}
          </span>
        </span>
        <span className="text-text-secondary">
          Invested:{' '}
          <span className="text-text-primary font-mono tabular-nums">
            {m.total_invested != null ? `${m.total_invested.toFixed(1)}%` : '—'}
          </span>
        </span>
      </div>
    </div>
  );
}
