import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import type { IntelligenceWhyDesk } from '@/lib/twelve-x/types';
import OppositionLedger from './OppositionLedger';

function desk(partial: Partial<IntelligenceWhyDesk> & Pick<IntelligenceWhyDesk, 'broker' | 'classification'>): IntelligenceWhyDesk {
  return {
    relevance: 0.9,
    conviction: 'high',
    direction: 'bullish',
    reason: 'Strong fundamentals',
    ...partial,
  };
}

describe('OppositionLedger', () => {
  it('renders every ledger class including superseded and invalidated', () => {
    const html = renderToStaticMarkup(
      createElement(OppositionLedger, {
        desks: [
          desk({ broker: 'Broker A', classification: 'active' }),
          desk({ broker: 'Old Broker', classification: 'superseded', reason: 'Superseded by a newer opinion.' }),
          desk({ broker: 'Wrong Broker', classification: 'invalidated', direction: 'bearish' }),
        ],
      }),
    );
    expect(html).toContain('Desk ledger · 3');
    expect(html).toContain('Broker A');
    expect(html).toContain('Old Broker');
    expect(html).toContain('Superseded by a newer opinion.');
    expect(html).toContain('Wrong Broker');
    expect(html).toContain('Superseded · 1');
    expect(html).toContain('Invalidated · 1');
  });

  it('renders nothing when there are no desks', () => {
    const html = renderToStaticMarkup(createElement(OppositionLedger, { desks: [] }));
    expect(html).toBe('');
  });
});
