import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { barFillPct, tickPct } from '../../lib/twelve-x/consensus-bar';
import { ConsensusScoreBar } from './ConsensusScoreBars';

type Marker = {
  value: number | null | undefined;
  kind: 'actual' | 'prior' | 'ago' | 'baseline';
  label: string;
};

function render(value: number, markers?: Marker[]): string {
  return renderToStaticMarkup(createElement(ConsensusScoreBar, { value, markers }));
}

describe('ConsensusScoreBar', () => {
  it('renders a bull fill at the correct width for a positive value', () => {
    const html = render(1);
    expect(html).toContain('dbar-fill bull');
    expect(html).not.toContain('dbar-fill bear');
    // barFillPct(1) = min(1, 1/2)*50 = 25
    expect(barFillPct(1)).toBe(25);
    expect(html).toContain('width:25%');
  });

  it('renders a bear fill for a negative value', () => {
    const html = render(-1.5);
    expect(html).toContain('dbar-fill bear');
    expect(html).not.toContain('dbar-fill bull');
    // barFillPct(-1.5) = min(1, 1.5/2)*50 = 37.5
    expect(html).toContain(`width:${barFillPct(-1.5)}%`);
  });

  it('treats a zero value as bull (fill at 0 width)', () => {
    const html = render(0);
    expect(html).toContain('dbar-fill bull');
    expect(html).toContain('width:0%');
  });

  it('always renders the zero-center track', () => {
    expect(render(0.5)).toContain('dbar-zero');
  });

  it('renders no ticks when markers are omitted', () => {
    const html = render(0.8);
    expect(html).not.toContain('dbar-tick');
  });

  it('renders no ticks for an empty markers array', () => {
    const html = render(0.8, []);
    expect(html).not.toContain('dbar-tick');
  });

  it('renders a legend-coded tick per marker at its tickPct', () => {
    const markers: Marker[] = [
      { value: 1, kind: 'actual', label: 'Today actual' },
      { value: 0.5, kind: 'prior', label: 'Yesterday avg' },
      { value: -0.4, kind: 'ago', label: '5d-ago avg' },
      { value: 0, kind: 'baseline', label: 'Neutral' },
    ];
    const html = render(1, markers);

    // actual → t-actual
    expect(html).toContain('dbar-tick t-actual');
    expect(html).toContain(`left:calc(${tickPct(1)}% - 1px)`);
    // prior → t-yday (accent)
    expect(html).toContain('dbar-tick t-yday');
    expect(html).toContain(`left:calc(${tickPct(0.5)}% - 1px)`);
    // ago → t-ago (muted)
    expect(html).toContain('dbar-tick t-ago');
    expect(html).toContain(`left:calc(${tickPct(-0.4)}% - 1px)`);
    // baseline → t-yday (accent, same as prior)
    expect(html).toContain(`left:calc(${tickPct(0)}% - 1px)`);

    // four ticks rendered
    expect((html.match(/dbar-tick/g) ?? []).length).toBe(4);
  });

  it('includes the marker label in the tick title', () => {
    const html = render(1, [{ value: 0.5, kind: 'prior', label: 'Yesterday avg' }]);
    expect(html).toContain('Yesterday avg');
  });

  it('omits markers with a null/undefined value (partial-start series) but keeps finite neighbours', () => {
    const markers: Marker[] = [
      { value: 1, kind: 'actual', label: 'Today actual' },
      { value: null, kind: 'prior', label: 'Yesterday avg (n/a)' },
      { value: undefined, kind: 'ago', label: '5d-ago avg (n/a)' },
    ];
    const html = render(1, markers);

    // only the finite 'actual' marker renders — exactly one tick, no dead-center
    // 50% tick from the dropped null/undefined markers.
    expect((html.match(/dbar-tick/g) ?? []).length).toBe(1);
    expect(html).toContain('dbar-tick t-actual');
    expect(html).toContain(`left:calc(${tickPct(1)}% - 1px)`);
    // the null/undefined markers contribute neither a tick nor a title
    expect(html).not.toContain('t-yday');
    expect(html).not.toContain('t-ago');
    expect(html).not.toContain('Yesterday avg (n/a)');
    // and crucially no spurious centered tick (tickPct(null) would have been 50)
    expect(html).not.toContain('left:calc(50% - 1px)');
  });
});
