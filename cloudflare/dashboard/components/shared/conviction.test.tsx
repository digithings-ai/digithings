import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import { ConvictionMeter } from './conviction-meter';
import { SignedConvictionBadge } from './signed-conviction-badge';

describe('ConvictionMeter (F6 unsigned cyan)', () => {
  it('renders `value` filled pips out of `max` with an sr-only label', () => {
    const html = renderToStaticMarkup(
      createElement(ConvictionMeter, { value: 2, max: 3, srLabel: 'Conviction 2 of 3' })
    );
    expect((html.match(/data-filled="true"/g) ?? []).length).toBe(2);
    expect((html.match(/data-filled="false"/g) ?? []).length).toBe(1);
    expect(html).toContain('Conviction 2 of 3');
  });
});

describe('SignedConvictionBadge (F6 signed)', () => {
  it('prefixes a sign and is the up/red semantic only', () => {
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: 3 }))).toContain('+3');
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: 3 }))).toContain('text-up');
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: -2 }))).toContain('−2');
    expect(renderToStaticMarkup(createElement(SignedConvictionBadge, { value: -2 }))).toContain('text-down');
  });
});
