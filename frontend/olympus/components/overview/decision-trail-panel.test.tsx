import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it } from 'vitest';
import { DecisionTrailPanel, type DecisionTrailProps } from './decision-trail-panel';
import type { PipelineTickerDoc } from '@/lib/types';

function render(props: DecisionTrailProps): string {
  return renderToStaticMarkup(createElement(DecisionTrailPanel, props));
}

const DEBATE: PipelineTickerDoc = {
  document_key: 'deliberation/NVDA',
  ticker: 'NVDA',
  payload: { net_stance: 'bullish' },
};

describe('DecisionTrailPanel', () => {
  it('shows an honest empty state naming the last run date', () => {
    const html = render({
      latestDate: '2026-06-13',
      deliberations: [],
      hasPmMemo: false,
      hasDigest: false,
    });
    expect(html).toContain('No decision artifacts');
    expect(html).toContain('2026-06-13');
  });

  it('renders rows for deliberations, PM memo, and digest when present', () => {
    const html = render({
      latestDate: '2026-06-13',
      deliberations: [DEBATE],
      hasPmMemo: true,
      hasDigest: true,
    });
    expect(html).toContain('Deliberations');
    expect(html).toContain('NVDA');
    expect(html).toContain('PM allocation memo');
    expect(html).toContain('Daily digest');
  });

  it('omits the risk-debate row until PR1b wires it', () => {
    const html = render({
      latestDate: '2026-06-13',
      deliberations: [DEBATE],
      hasPmMemo: false,
      hasDigest: false,
    });
    expect(html).not.toContain('Risk debate');
  });
});
