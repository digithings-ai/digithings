import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { wilsonInterval } from '@/lib/twelve-x/wilson';
import WilsonStat, { WilsonStat as NamedWilsonStat } from './WilsonStat';

describe('WilsonStat', () => {
  it('renders the rate with k/n and the 95% CI', () => {
    const html = renderToStaticMarkup(
      createElement(WilsonStat, { label: 'All ideas', interval: wilsonInterval(7, 10) }),
    );
    expect(html).toContain('All ideas');
    expect(html).toContain('70%');
    expect(html).toContain('7/10');
    expect(html).toContain('95% CI');
  });

  it('renders an em dash when n is 0', () => {
    const html = renderToStaticMarkup(
      createElement(WilsonStat, { label: 'Short', interval: wilsonInterval(0, 0) }),
    );
    expect(html).toContain('Short');
    expect(html).toContain('—');
    expect(html).not.toContain('95% CI');
  });

  it('flags small-n samples below the insufficientN threshold', () => {
    const small = renderToStaticMarkup(
      createElement(WilsonStat, { label: 'Long', interval: wilsonInterval(2, 3) }),
    );
    expect(small).toContain('small n');
    const enough = renderToStaticMarkup(
      createElement(WilsonStat, {
        label: 'Long',
        interval: wilsonInterval(8, 12),
        insufficientN: 10,
      }),
    );
    expect(enough).not.toContain('small n');
  });

  it('exposes a named export alongside the default', () => {
    expect(NamedWilsonStat).toBe(WilsonStat);
  });
});
