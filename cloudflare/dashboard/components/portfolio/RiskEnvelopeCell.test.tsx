import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { isQuoteFresh, LIVE_QUOTE_FRESH_MS, type Valuation } from '@/lib/live-valuation';
import RiskEnvelopeCell from './RiskEnvelopeCell';

/**
 * A display-layer valuation: `unrealizedPct` is percent points vs entry, never a price.
 *
 * `ageMs` defaults to a comfortably FRESH 30s so the pre-existing assertions keep meaning what
 * they meant; the stale cases pass an explicit age. `isFresh` is derived the way every consumer
 * must derive its label — `source === 'live'` AND the age test, never one or the other.
 */
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

function cell(props: Partial<Parameters<typeof RiskEnvelopeCell>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(RiskEnvelopeCell, {
      stopLossPct: -10,
      targetPctGain: 10,
      horizonDays: null,
      ...props,
    })
  );
}

describe('RiskEnvelopeCell', () => {
  it('renders stop, target, and horizon when populated', () => {
    const html = renderToStaticMarkup(
      createElement(RiskEnvelopeCell, { stopLossPct: -8, targetPctGain: 15, horizonDays: 30 })
    );
    expect(html).toContain('-8.0%');
    expect(html).toContain('+15.0%');
    expect(html).toContain('30d');
  });

  it('renders a quiet placeholder when no risk fields are set', () => {
    const html = renderToStaticMarkup(
      createElement(RiskEnvelopeCell, { stopLossPct: null, targetPctGain: null, horizonDays: null })
    );
    expect(html).toContain('—');
    expect(html).not.toContain('%');
  });

  // #1834 — the current-position marker. The axis is percent-vs-entry, running from the stop
  // (-10 here) at the left end through entry (0) to the target (+10) at the right end.
  it('places an in-range mark proportionally between the stop and target ends', () => {
    const html = cell({ valuation: val(5) }); // (5 + 10) / 20 = 0.75
    expect(html).toContain('data-live-mark');
    expect(html).toContain('left:75%');
    expect(html).toContain('translateX(-50%)');
    expect(html).not.toContain('data-pin-edge');
  });

  it('lands a flat position exactly on the entry tick', () => {
    // Asymmetric envelope so a coincidence at 50% cannot pass this by accident: entry sits at
    // 10 / (10 + 30) = 25%, and a 0% reading must land on the same offset.
    const html = cell({ stopLossPct: -10, targetPctGain: 30, valuation: val(0) });
    expect(html.match(/left:25%/g)).toHaveLength(2);
  });

  it('pins a reading beyond the target at the end instead of overflowing it', () => {
    const html = cell({ valuation: val(30) }); // raw fraction 2.0
    expect(html).toContain('left:100%');
    expect(html).not.toContain('left:200%');
    expect(html).toContain('data-pin-edge="target"');
    // Distinguishable from "exactly at the boundary" by SHAPE, not colour: an outward caret
    // (border triangle) replaces the in-range tick.
    expect(html).toContain('border-l-[7px]');
    expect(html).not.toContain('w-[3px]');
    expect(html).toContain('beyond the +10.0% target');
  });

  it('pins a reading through the stop at the low end instead of a negative offset', () => {
    const html = cell({ valuation: val(-40) }); // raw fraction -1.5
    expect(html).toContain('left:0%');
    expect(html).not.toContain('left:-');
    expect(html).toContain('data-pin-edge="stop"');
    expect(html).toContain('border-r-[7px]');
    expect(html).toContain('through the stop');
  });

  it('hides the mark when the valuation is unavailable rather than parking it mid-range', () => {
    // Asymmetric so the entry tick is at 25%: a stray `left:50%` could only be a fabricated
    // midpoint mark, which is indistinguishable from a real reading and worse than none.
    const html = cell({
      stopLossPct: -10,
      targetPctGain: 30,
      valuation: {
        source: 'unavailable',
        price: null,
        unrealizedPct: null,
        asOf: null,
        isFresh: false,
        ageMs: null,
      },
    });
    expect(html).not.toContain('data-live-mark');
    expect(html).not.toContain('left:50%');
  });

  it('hides the mark when the envelope has no width (the 50% fallback is fabricated)', () => {
    const html = cell({ stopLossPct: 0, targetPctGain: 0, valuation: val(5) });
    expect(html).not.toContain('data-live-mark');
  });

  it('announces the mark and its basis in text, never colour alone', () => {
    const live = cell({ valuation: val(5) });
    expect(live).toContain('class="sr-only"');
    expect(live).toContain('Now +5.0% vs entry live, inside the stop-to-target range.');
    expect(live).toContain('title="Now +5.0% vs entry live, inside the stop-to-target range."');
    const close = cell({ valuation: val(5, 'close') });
    expect(close).toContain('Now +5.0% vs entry at the last close, inside the stop-to-target range.');
    expect(close).not.toContain('vs entry live');
  });

  // #1833 — `prices_live` rows persist indefinitely (no DELETE path, publisher idle outside
  // 13:00–01:00 UTC Mon–Fri), so the presence of a quote says nothing about its recency. The
  // marker still gets drawn from a stale quote — it is the best mark available — but the spoken
  // label states the quote's age instead of calling it live.
  it('states the age instead of "live" once the quote is past the freshness threshold', () => {
    const html = cell({ valuation: val(5, 'live', 18.63 * 3_600_000) });
    expect(html).toContain('Now +5.0% vs entry on a quote 18h old, inside the stop-to-target range.');
    expect(html).not.toContain('vs entry live');
    // The reading is still plotted: the value is unchanged, only the claim about it is.
    expect(html).toContain('data-live-mark');
    expect(html).toContain('left:75%');
  });

  it('says "live" exactly AT the threshold and stops one millisecond past it', () => {
    expect(cell({ valuation: val(5, 'live', LIVE_QUOTE_FRESH_MS) })).toContain('vs entry live');
    const past = cell({ valuation: val(5, 'live', LIVE_QUOTE_FRESH_MS + 1) });
    expect(past).not.toContain('vs entry live');
    expect(past).toContain('vs entry on a quote 5m old');
  });

  it('declines the claim when the quote age is unknown, rather than assuming it is current', () => {
    const html = cell({ valuation: val(5, 'live', null) });
    expect(html).toContain('vs entry on a quote of unknown age');
    expect(html).not.toContain('vs entry live');
  });

  it('never calls a close a stale quote — the gate is source AND freshness, not !isFresh', () => {
    // A close is `isFresh: false` like a stale quote is, so a consumer branching on freshness
    // alone would describe the nightly record as a quote that stopped ticking.
    const html = cell({ valuation: val(5, 'close', 1_000) });
    expect(html).toContain('vs entry at the last close');
    expect(html).not.toContain('on a quote');
    expect(html).not.toContain('vs entry live');
  });
});
