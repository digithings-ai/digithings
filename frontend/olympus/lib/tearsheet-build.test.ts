import { describe, expect, it } from 'vitest';
import { buildOlympusTearsheet } from './observability-queries';
import type { TableRow } from './database.types';

const navRow = (
  date: string,
  nav: number,
  invested_pct: number | null = 75,
): TableRow<'nav_history'> => ({
  date,
  nav,
  cash_pct: invested_pct == null ? null : 100 - invested_pct,
  invested_pct,
});

const dec = (
  run_date: string,
  ticker: string,
  conviction: number | null,
  status: string,
  alpha: number | null,
  actual_return: number | null,
): TableRow<'decision_log'> => ({
  id: `${ticker}-${run_date}`,
  run_id: 'r1',
  run_date,
  ticker,
  stance: 'buy',
  conviction,
  thesis: null,
  benchmark: 'SPY',
  holding_days: 10,
  status: status as 'pending' | 'resolved',
  actual_return,
  alpha,
  reflection: null,
  resolved_at: null,
  created_at: null,
});

describe('buildOlympusTearsheet', () => {
  it('single NAV point → navPoints 1, live track has 1 equity point, no drawdown blow-up', () => {
    const t = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 99.32)],
      decisions: [],
      metrics: null,
      attribution: [],
      now: new Date('2026-06-24T00:00:00Z'),
    });
    expect(t.navPoints).toBe(1);
    expect(t.live.engine).toBe('live');
    expect(t.live.strategy).toBe('Olympus');
    expect(t.live.symbol).toBe('AI-INTELLIGENCE');
    expect(t.live.equity_curve).toHaveLength(1);
    expect(t.inceptionDate).toBe('2026-06-23');
    expect(t.latestNav).toBe(99.32);
  });

  it('≥2 NAV points → equity + drawdown curves; sharpe from NAV-derived metrics', () => {
    const t = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102), navRow('2026-06-25', 101)],
      decisions: [],
      metrics: null,
      attribution: [],
      now: new Date(),
    });
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
      metrics: null,
      attribution: [],
      now: new Date(),
    });
    expect(t.nResolved).toBe(2);
    expect(t.nPending).toBe(1);
    expect(t.decision.n_trades).toBe(2); // only resolved feed the track record
    expect(t.decision.hit_rate).toBe(0.5);
    expect(t.decisionRows).toHaveLength(3); // all rows shown in the small table
  });

  it('prefers persisted portfolio_metrics sharpe over NAV-derived', () => {
    const t = buildOlympusTearsheet({
      nav: [navRow('2026-06-23', 100), navRow('2026-06-24', 102)],
      decisions: [],
      metrics: {
        id: 'm',
        date: '2026-06-24',
        pnl_pct: 2,
        sharpe: 1.9,
        volatility: 12,
        max_drawdown: -3,
        alpha: 0.5,
        invested_pct: 75,
        generated_at: null,
      } as TableRow<'portfolio_metrics'>,
      attribution: [],
      now: new Date(),
    });
    expect(t.live.sharpe_ratio).toBe(1.9);
  });
});
