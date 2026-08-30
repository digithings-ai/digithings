import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { PipelineTab } from './pipeline-tab';

describe('PipelineTab', () => {
  it('renders pipeline fields', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineTab, {
        api: null,
        lastVersionId: null,
        getFn: vi.fn(),
        saveFn: vi.fn(),
      }),
    );
    expect(html).toContain('settings-pipeline-tab');
    expect(html).toContain('pipeline-watchlist');
    expect(html).toContain('pipeline-themes');
    expect(html).toContain('pipeline-budget');
  });

  it('saveFn contract includes watchlist/themes/budget', async () => {
    const saveFn = vi.fn(async () => ({
      version_id: 'v2',
      profile_key: 'workspace',
      schema_version: 1,
      label: 'Workspace overlay',
      supersedes_id: null,
      recorded_at: '2026-08-30T00:00:00Z',
    }));
    await saveFn(
      { accessToken: 'tok', functionsBaseUrl: 'https://example.test/functions/v1' },
      {
        profile_key: 'workspace',
        label: 'Workspace overlay',
        watchlist: ['AAPL', 'MSFT'],
        themes: ['ai'],
        research_budget_usd: 10,
        expected_version_id: 'v1',
      },
    );
    expect(saveFn.mock.calls[0]![1].watchlist).toEqual(['AAPL', 'MSFT']);
    expect(saveFn.mock.calls[0]![1].research_budget_usd).toBe(10);
  });
});
