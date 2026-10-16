/**
 * Tests for the §6.1 `buildPortfolioData` assembler: invested precedence vs
 * the clamped envelope, the committed-book gate, and the seam object.
 */
import { describe, it, expect } from 'vitest';
import { buildPortfolioData } from './portfolio';
import type { BookPositionInput } from './book';
import type { PortfolioNavTipInput } from './portfolio';

const positions: BookPositionInput[] = [
  { ticker: 'XLV', weightActual: 20 },
  { ticker: 'DBO', weightActual: 15.13 },
];

const tip = (partial: Partial<PortfolioNavTipInput> = {}): PortfolioNavTipInput => ({
  date: '2026-09-24',
  nav: 99.909,
  source: 'legacy_nav_history',
  contract: 'legacy_estimate',
  investedPct: 35.13,
  cashPct: 64.87,
  dayReturnPct: null,
  ...partial,
});

describe('buildPortfolioData (§6.1)', () => {
  it('serves the raw tip KPI inside the clamped envelope', () => {
    const result = buildPortfolioData({
      snapshotDate: '2026-09-24',
      positionDates: ['2026-09-24'],
      positions,
      navRows: [tip()],
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.bookAsOf).toBe('2026-09-24');
    expect(result.data.navTip?.investedPct).toBeCloseTo(35.13, 4);
    expect(result.data.invested.kpiPct).toBeCloseTo(35.13, 4);
    expect(result.data.invested.envelopePct).toBeCloseTo(35.13, 4);
    expect(result.data.invested.cashPct).toBeCloseTo(64.87, 4);
    expect(result.data.invested.definition).toBe('accounting_nav_tip');
    const weights = result.data.positions.reduce((s, r) => s + r.scaledWeightPct, 0);
    expect(weights).toBeCloseTo(35.13, 3);
  });

  it('keeps an over-100 tip raw on the KPI while rows stay in the envelope', () => {
    const result = buildPortfolioData({
      snapshotDate: '2026-09-24',
      positionDates: ['2026-09-24'],
      positions,
      navRows: [tip({ investedPct: 135 })],
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.invested.kpiPct).toBe(135);
    expect(result.data.invested.envelopePct).toBe(100);
    const weights = result.data.positions.reduce((s, r) => s + r.scaledWeightPct, 0);
    expect(weights).toBeCloseTo(100, 3);
  });

  it('falls back to book weights (empty book stays book_weights, client parity)', () => {
    const noTip = buildPortfolioData({
      snapshotDate: '2026-09-24',
      positionDates: ['2026-09-24'],
      positions,
      navRows: [tip({ investedPct: null })],
    });
    expect(noTip.ok && noTip.data.invested.definition).toBe('book_weights');

    // Client parity (`PortfolioShellInner.tsx`): the book-weight sum is
    // passed as-is, so an empty book resolves to book_weights 0 — not
    // metrics. The metrics leg is unit-covered in `invested.test.ts`.
    const metrics = buildPortfolioData({
      snapshotDate: '2026-09-24',
      positionDates: ['2026-09-24'],
      positions: [],
      navRows: [tip({ investedPct: null })],
      metricsInvestedPct: 28,
    });
    expect(metrics.ok && metrics.data.invested.definition).toBe('book_weights');
    expect(metrics.ok && metrics.data.invested.kpiPct).toBe(0);
  });

  it('returns not_found instead of substituting the latest position date', () => {
    const missing = buildPortfolioData({
      snapshotDate: null,
      positionDates: ['2026-09-24'],
      positions,
      navRows: [tip()],
    });
    expect(missing.ok).toBe(false);
    if (missing.ok) return;
    expect(missing.error.code).toBe('not_found');

    const uncommitted = buildPortfolioData({
      snapshotDate: '2026-09-23',
      positionDates: ['2026-09-24'],
      positions,
      navRows: [tip()],
    });
    expect(uncommitted.ok).toBe(false);
  });

  it('nulls the tip day return across a seam and reports it', () => {
    const result = buildPortfolioData({
      snapshotDate: '2026-09-24',
      positionDates: ['2026-09-24'],
      positions,
      navRows: [
        {
          date: '2026-09-23',
          nav: 100,
          source: 'legacy_nav_history',
          contract: 'legacy_estimate',
        },
        {
          date: '2026-09-24',
          nav: 110,
          source: 'finalized_accounting',
          contract: 'finalized_accounting',
          seriesSeam: true,
          investedPct: 35.13,
          cashPct: 64.87,
          dayReturnPct: 10,
        },
      ],
    });
    expect(result.ok).toBe(true);
    if (!result.ok) return;
    expect(result.data.navTip?.dayReturnPct).toBeNull();
    expect(result.data.seam.crossesNavSeam).toBe(true);
  });

  it('reports signed metrics lag (metrics lag vs nav lag)', () => {
    const lagging = buildPortfolioData({
      snapshotDate: '2026-09-24',
      positionDates: ['2026-09-24'],
      positions,
      navRows: [tip()],
      metricsAsOf: '2026-09-23',
    });
    expect(lagging.ok && lagging.data.seam.lagDays).toBe(1);
    expect(lagging.ok && lagging.data.seam.lagDirection).toBe('metrics lag');

    const ahead = buildPortfolioData({
      snapshotDate: '2026-09-24',
      positionDates: ['2026-09-24'],
      positions,
      navRows: [tip()],
      metricsAsOf: '2026-09-25',
    });
    expect(ahead.ok && ahead.data.seam.lagDays).toBe(-1);
    expect(ahead.ok && ahead.data.seam.lagDirection).toBe('nav lag');
  });
});
