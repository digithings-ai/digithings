import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, it, expect } from 'vitest';
import RiskEnvelopeCell from './RiskEnvelopeCell';

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
});
