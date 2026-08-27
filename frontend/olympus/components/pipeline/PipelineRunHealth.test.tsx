import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/observability-queries', () => ({
  fetchAtlasRunDiagnostics: vi.fn(() => Promise.resolve([])),
}));

import PipelineRunHealth from './PipelineRunHealth';

describe('PipelineRunHealth', () => {
  it('renders a collapsible Run health disclosure for the selected date', () => {
    const html = renderToStaticMarkup(createElement(PipelineRunHealth, { date: '2026-08-06' }));
    expect(html).toContain('data-testid="pipeline-run-health"');
    expect(html).toContain('Run health');
    expect(html).toContain('2026-08-06');
    expect(html).toContain('<details');
  });
});
