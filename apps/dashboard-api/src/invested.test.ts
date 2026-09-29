/**
 * Parity tests vs `resolveInvestedPct` in
 * `apps/dashboard/lib/performance-ssot.ts` (client) and CONTRACT.md §6.1:
 * NAV tip → book weights → portfolio_metrics → null, with the raw-KPI /
 * clamped-envelope split.
 */
import { describe, it, expect } from 'vitest';
import { resolveInvestedPct, buildInvestedEnvelope } from './invested';

describe('resolveInvestedPct precedence (client parity)', () => {
  it('prefers the accounting NAV tip', () => {
    expect(
      resolveInvestedPct({
        tipInvestedPct: 35.13,
        bookWeightInvestedPct: 40,
        metricsInvestedPct: 30,
      }),
    ).toEqual({ investedPct: 35.13, definition: 'accounting_nav_tip' });
  });

  it('does not clamp a >100 tip — the KPI wears the raw value', () => {
    expect(
      resolveInvestedPct({
        tipInvestedPct: 135,
        bookWeightInvestedPct: 40,
        metricsInvestedPct: 30,
      }),
    ).toEqual({ investedPct: 135, definition: 'accounting_nav_tip' });
  });

  it('falls back to non-CASH book weights when the tip is missing', () => {
    expect(
      resolveInvestedPct({
        tipInvestedPct: null,
        bookWeightInvestedPct: 42.5,
        metricsInvestedPct: 30,
      }),
    ).toEqual({ investedPct: 42.5, definition: 'book_weights' });
  });

  it('falls back to portfolio_metrics only when tip and book are missing', () => {
    expect(
      resolveInvestedPct({
        tipInvestedPct: null,
        metricsInvestedPct: 28,
        bookWeightInvestedPct: null,
      }),
    ).toEqual({ investedPct: 28, definition: 'portfolio_metrics' });
  });

  it('returns unavailable (never invents) when every source is missing', () => {
    expect(
      resolveInvestedPct({
        tipInvestedPct: null,
        bookWeightInvestedPct: null,
        metricsInvestedPct: null,
      }),
    ).toEqual({ investedPct: null, definition: 'unavailable' });
  });

  it('ignores negative / non-finite sources', () => {
    expect(
      resolveInvestedPct({
        tipInvestedPct: -5,
        bookWeightInvestedPct: NaN,
        metricsInvestedPct: 28,
      }),
    ).toEqual({ investedPct: 28, definition: 'portfolio_metrics' });
  });
});

describe('buildInvestedEnvelope (§6.1 KPI vs envelope split)', () => {
  it('keeps kpi raw while the envelope clamps at 100', () => {
    const envelope = buildInvestedEnvelope(
      { investedPct: 135, definition: 'accounting_nav_tip' },
      40,
    );
    expect(envelope.kpiPct).toBe(135);
    expect(envelope.envelopePct).toBe(100);
    expect(envelope.cashPct).toBe(0);
  });

  it('passes a normal tip straight through (kpi == envelope)', () => {
    const envelope = buildInvestedEnvelope(
      { investedPct: 35.13, definition: 'accounting_nav_tip' },
      35.13,
    );
    expect(envelope.kpiPct).toBeCloseTo(35.13, 4);
    expect(envelope.envelopePct).toBeCloseTo(35.13, 4);
    expect(envelope.cashPct).toBeCloseTo(64.87, 4);
  });

  it('falls back to the held sum when nothing resolved', () => {
    const envelope = buildInvestedEnvelope(
      { investedPct: null, definition: 'unavailable' },
      42.5,
    );
    expect(envelope.kpiPct).toBeNull();
    expect(envelope.envelopePct).toBeCloseTo(42.5, 4);
    expect(envelope.cashPct).toBeCloseTo(57.5, 4);
  });
});
