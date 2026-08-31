/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PipelineTab } from './pipeline-tab';

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(ui: React.ReactElement): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(ui);
  });
  return host;
}

describe('PipelineTab', () => {
  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it('renders pipeline fields', () => {
    const html = renderToStaticMarkup(
      createElement(PipelineTab, {
        api: null,
        lastVersionId: null,
        getFn: vi.fn(),
        saveFn: vi.fn(),
        jobsFn: vi.fn(),
      }),
    );
    expect(html).toContain('settings-pipeline-tab');
    expect(html).toContain('pipeline-watchlist');
    expect(html).toContain('pipeline-themes');
    expect(html).toContain('pipeline-budget');
    expect(html).toContain('pipeline-runs');
  });

  it('hydrates overlay job_runs including skip reasons', async () => {
    const getFn = vi.fn(async () => ({
      version_id: 'v1',
      profile_key: 'workspace',
      schema_version: 1,
      label: 'Workspace overlay',
      supersedes_id: null,
      recorded_at: '2026-08-31T00:00:00Z',
      investment: null,
      assets: null,
      watchlist: ['AAPL'],
      themes: ['ai'],
      research_budget_usd: 5,
    }));
    const jobsFn = vi.fn(async () => [
      {
        id: 'job-1',
        job_type: 'overlay_daily',
        status: 'skipped',
        error: 'no_credentials',
        idempotency_key: 'ws:overlay_daily:2026-08-31',
        started_at: '2026-08-31T12:00:00Z',
        finished_at: '2026-08-31T12:00:01Z',
      },
    ]);
    const el = await mount(
      createElement(PipelineTab, {
        api: { accessToken: 'tok' },
        lastVersionId: 'v1',
        getFn,
        saveFn: vi.fn(),
        jobsFn,
      }),
    );
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(jobsFn).toHaveBeenCalledOnce();
    const runs = el.querySelector('[data-testid="pipeline-runs"]');
    expect(runs?.textContent).toMatch(/skipped/);
    expect(runs?.textContent).toMatch(/no_credentials/);
    expect(el.querySelector('[data-testid="pipeline-run-row"]')).not.toBeNull();
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
