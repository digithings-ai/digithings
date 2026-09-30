import { describe, expect, it } from 'vitest';
import type { FxIdeaEvalRow } from './types';
import { deriveTodayKpis, evalInWindow, formatCountdown, nextHighImpactEvent } from './kpis';

const NOW = new Date('2026-06-22T10:00:00Z');

function ev(run_date: string, win: boolean | null, status = 'resolved'): FxIdeaEvalRow {
  return {
    run_date,
    rank: 1,
    horizon_days: 0,
    pair: 'EUR/USD',
    direction: 'long',
    status,
    entry_date: null,
    exit_date: null,
    entry_fix: null,
    exit_fix: null,
    ret: null,
    hold_return: null,
    sigma_entry: null,
    hit: null,
    directional_win: win,
    significant_hit: null,
    n_sessions: 1,
    as_of: `${run_date}T00:00:00Z`,
  };
}

const events = [
  { impact: 'high', event_name: 'Past NFP', country: 'US', event_datetime_utc: '2026-06-22T08:00:00Z' },
  { impact: 'medium', event_name: 'Soon but medium', country: 'EU', event_datetime_utc: '2026-06-22T10:30:00Z' },
  { impact: 'high', event_name: 'Later CPI', country: 'UK', event_datetime_utc: '2026-06-22T13:30:00Z' },
  { impact: 'high', event_name: 'Even later', country: 'JP', event_datetime_utc: '2026-06-23T01:00:00Z' },
  { impact: 'high', event_name: 'No time', country: 'CA', event_datetime_utc: null },
];

describe('nextHighImpactEvent', () => {
  it('picks the soonest future high-impact release and ignores medium, past and untimed', () => {
    const next = nextHighImpactEvent(events, NOW);
    expect(next?.name).toBe('Later CPI');
    expect(next?.minutesAway).toBe(210);
  });
  it('is null when nothing qualifies', () => {
    expect(nextHighImpactEvent([events[0], events[1]], NOW)).toBeNull();
  });
});

describe('evalInWindow', () => {
  it('keeps only rows inside the trailing 30 days', () => {
    const rows = [ev('2026-05-01', true), ev('2026-05-23', true), ev('2026-06-20', false)];
    expect(evalInWindow(rows, NOW).map((r) => r.run_date)).toEqual(['2026-05-23', '2026-06-20']);
  });
});

describe('deriveTodayKpis', () => {
  const base = {
    runDate: '2026-06-22',
    ideas: [{ rank: 1 }, { rank: 2 }, { rank: 3 }],
    disputedCount: 2,
    briefs: [{ broker_name: 'A' }, { broker_name: 'A' }, { broker_name: 'B' }, { broker_name: null }],
    digest: null,
    events,
    now: NOW,
  };

  it('computes a Wilson hit rate over resolved rows only', () => {
    const k = deriveTodayKpis({
      ...base,
      ideaEval: [
        ev('2026-06-10', true),
        ev('2026-06-11', true),
        ev('2026-06-12', false),
        ev('2026-06-13', null, 'carried'),
      ],
    });
    expect(k.hit?.n).toBe(3);
    expect(k.hit?.k).toBe(2);
    expect(k.hit?.rate).toBeCloseTo(2 / 3);
    expect(k.hit!.low).toBeLessThan(k.hit!.rate);
    expect(k.hit!.high).toBeGreaterThan(k.hit!.rate);
    expect(k.ideaCount).toBe(3);
    expect(k.disputedCount).toBe(2);
    expect(k.briefCount).toBe(4);
    expect(k.brokerCount).toBe(2);
  });

  it('has no hit rate when nothing resolved and prefers the digest broker count', () => {
    const k = deriveTodayKpis({
      ...base,
      digest: { broker_count: 9 },
      ideaEval: [ev('2026-06-13', null, 'carried')],
    });
    expect(k.hit).toBeNull();
    expect(k.brokerCount).toBe(9);
  });

  it('reports no broker count when briefs are anonymous and there is no digest', () => {
    const k = deriveTodayKpis({ ...base, briefs: [{ broker_name: null }], ideaEval: [] });
    expect(k.brokerCount).toBeNull();
  });
});

describe('formatCountdown', () => {
  it('formats minutes, hours and now', () => {
    expect(formatCountdown(0)).toBe('now');
    expect(formatCountdown(35)).toBe('in 35m');
    expect(formatCountdown(120)).toBe('in 2h');
    expect(formatCountdown(130)).toBe('in 2h 10m');
  });
});
