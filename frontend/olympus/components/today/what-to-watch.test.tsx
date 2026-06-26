import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect, vi } from 'vitest';

vi.mock('next/link', () => ({ default: (props: { children?: unknown }) => props.children }));

import { WhatToWatch } from './what-to-watch';

const actionables = [
  { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs; pressures EM' },
  { label: 'Trim XLI on weakness', priority: 2, rationale: 'industrials rolling over' },
];
const risks = [
  { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 },
];

describe('WhatToWatch', () => {
  it('renders ranked actionables with rationale and the read deep-link', () => {
    const html = renderToStaticMarkup(
      createElement(WhatToWatch, { actionables, risks, asOfDate: '2026-06-24' })
    );
    expect(html).toContain('Monitor DXY above 120.4');
    expect(html).toContain('near YTD highs');
    expect(html).toContain('BOJ intervention');
    expect(html).toContain('48h'); // horizon
    expect(html).toContain('full read'); // CTA copy
  });
  it('renders only actionables when there are no risks', () => {
    const html = renderToStaticMarkup(
      createElement(WhatToWatch, { actionables, risks: [], asOfDate: null })
    );
    expect(html).toContain('Monitor DXY above 120.4');
    expect(html).not.toContain('Tail risks');
  });
  it('renders nothing when both are empty', () => {
    const html = renderToStaticMarkup(
      createElement(WhatToWatch, { actionables: [], risks: [], asOfDate: null })
    );
    expect(html).toBe('');
  });
});
