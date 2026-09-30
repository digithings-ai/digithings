import { describe, expect, it } from 'vitest';
import { isQuoteFresh, LIVE_QUOTE_FRESH_MS, type Valuation } from './live-valuation';
import { riskEnvelopeView } from './holding-risk-envelope';

function val(
  unrealizedPct: number | null,
  source: Valuation['source'] = 'live',
  ageMs: number | null = 30_000
): Valuation {
  return {
    source,
    price: 123,
    unrealizedPct,
    asOf: '2026-08-03T18:23:00.000Z',
    isFresh: source === 'live' && isQuoteFresh(ageMs),
    ageMs,
  };
}

const current = (v: ReturnType<typeof riskEnvelopeView>) => v.markers.find((m) => m.kind === 'current');

describe('riskEnvelopeView', () => {
  it('builds a percent-vs-entry axis with entry at 0 and stop/target at the ends', () => {
    const v = riskEnvelopeView(-8, 15, val(5));
    expect([v.low, v.high]).toEqual([-8, 15]);
    expect(v.markers.map((m) => [m.kind, m.value])).toEqual([
      ['entry', 0],
      ['stop', -8],
      ['target', 15],
      ['current', 5],
    ]);
    expect(v.mark?.pinned).toBeNull();
    expect(v.mark?.label).toBe('Now +5.0% vs entry live, inside the stop-to-target range.');
  });

  it('pins a reading beyond the target and through the stop, with distinct wording', () => {
    const over = riskEnvelopeView(-10, 10, val(30));
    expect(over.mark?.pinned).toBe('target');
    expect(over.mark?.label).toContain('beyond the +10.0% target');
    const under = riskEnvelopeView(-10, 10, val(-40));
    expect(under.mark?.pinned).toBe('stop');
    expect(under.mark?.label).toContain('through the stop');
  });

  it('does not call the far end a target or stop on a half envelope', () => {
    expect(riskEnvelopeView(-10, null, val(3)).mark?.pinned).toBe('target');
    expect(riskEnvelopeView(-10, null, val(3)).mark?.label).toContain('above the plotted range');
    expect(riskEnvelopeView(null, 10, val(-3)).mark?.label).toContain('below the plotted range');
  });

  it('hides the mark when unavailable, non-finite, or the envelope has no width', () => {
    const none: Valuation = { source: 'unavailable', price: null, unrealizedPct: null, asOf: null, isFresh: false, ageMs: null };
    expect(riskEnvelopeView(-10, 30, none).mark).toBeNull();
    expect(current(riskEnvelopeView(-10, 30, none))).toBeUndefined();
    expect(riskEnvelopeView(-10, 30, val(Number.NaN)).mark).toBeNull();
    expect(riskEnvelopeView(0, 0, val(5)).mark).toBeNull();
    expect(riskEnvelopeView(-10, 30).mark).toBeNull();
  });

  it('gates the word "live" on source AND freshness', () => {
    expect(riskEnvelopeView(-10, 10, val(5, 'live', LIVE_QUOTE_FRESH_MS)).mark?.label).toContain('vs entry live');
    const past = riskEnvelopeView(-10, 10, val(5, 'live', LIVE_QUOTE_FRESH_MS + 1)).mark?.label;
    expect(past).toContain('vs entry on a quote 5m old');
    expect(past).not.toContain('vs entry live');
    expect(riskEnvelopeView(-10, 10, val(5, 'live', 18.63 * 3_600_000)).mark?.label).toContain('on a quote 18h old');
    expect(riskEnvelopeView(-10, 10, val(5, 'live', null)).mark?.label).toContain('on a quote of unknown age');
  });

  it('never calls a close a stale quote', () => {
    const label = riskEnvelopeView(-10, 10, val(5, 'close', 1_000)).mark?.label;
    expect(label).toContain('vs entry at the last close');
    expect(label).not.toContain('on a quote');
  });

  it('still plots a stale quote (best mark available)', () => {
    expect(current(riskEnvelopeView(-10, 10, val(5, 'live', 18 * 3_600_000)))?.value).toBe(5);
  });
});
