import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { isQuoteFresh, type Valuation } from '@/lib/live-valuation';
import RiskEnvelopeCell from './RiskEnvelopeCell';

/** `unrealizedPct` is percent points vs entry, never a price. Geometry maths live in lib/holding-risk-envelope.test.ts. */
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
    createElement(RiskEnvelopeCell, { stopLossPct: -10, targetPctGain: 10, horizonDays: null, ...props })
  );
}

describe('RiskEnvelopeCell (kit RangeTrack adapter)', () => {
  it('renders stop, target, and horizon when populated', () => {
    const html = cell({ stopLossPct: -8, targetPctGain: 15, horizonDays: 30 });
    expect(html).toContain('-8.0%');
    expect(html).toContain('+15.0%');
    expect(html).toContain('30d');
  });

  it('draws the kit range track (not a hand-rolled bar) with stop/target as levels, never up/down', () => {
    const html = cell();
    expect(html).toContain('data-slot="range-track"');
    expect(html).toContain('data-kind="stop"');
    expect(html).toContain('data-kind="target"');
    expect(html).toContain('data-kind="entry"');
    expect(html).not.toContain('text-up');
    expect(html).not.toContain('text-down');
    expect(html).not.toContain('bg-up');
    expect(html).not.toContain('bg-down');
  });

  it('renders a quiet placeholder when no risk fields are set', () => {
    const html = cell({ stopLossPct: null, targetPctGain: null, horizonDays: null });
    expect(html).toContain('—');
    expect(html).not.toContain('%');
    expect(html).not.toContain('range-track');
  });

  it('plots the current reading proportionally and flags it', () => {
    const html = cell({ valuation: val(5) });
    expect(html).toContain('data-live-mark');
    expect(html).toContain('data-kind="current"');
    expect(html).toContain('x1="75"'); // (5 + 10) / 20
    expect(html).not.toContain('data-pin-edge');
  });

  it('pins an out-of-range reading with a caret shape and says so', () => {
    const over = cell({ valuation: val(30) });
    expect(over).toContain('data-pin-edge="target"');
    expect(over).toContain('data-pinned="high"');
    expect(over).toContain('beyond the +10.0% target');
    const under = cell({ valuation: val(-40) });
    expect(under).toContain('data-pin-edge="stop"');
    expect(under).toContain('through the stop');
  });

  it('hides the mark when unavailable instead of parking it mid-range', () => {
    const html = cell({
      valuation: { source: 'unavailable', price: null, unrealizedPct: null, asOf: null, isFresh: false, ageMs: null },
    });
    expect(html).not.toContain('data-live-mark');
    expect(html).not.toContain('data-kind="current"');
  });

  it('announces the mark and its basis in text, never colour alone', () => {
    const live = cell({ valuation: val(5) });
    expect(live).toContain('class="sr-only"');
    expect(live).toContain('Now +5.0% vs entry live, inside the stop-to-target range.');
    expect(cell({ valuation: val(5, 'close') })).toContain('vs entry at the last close');
  });
});
