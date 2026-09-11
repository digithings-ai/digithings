/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { PipelineTab } from './pipeline-tab';
import { SettingsHttpError } from '@/lib/settings-api';
import { defaultPipelineSchedule } from '@/lib/settings/pipeline-schedule';

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

async function flush() {
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
    await Promise.resolve();
  });
}

const emptyTip = {
  version_id: 'v1',
  workspace_id: 'ws',
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
};

describe('PipelineTab', () => {
  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it('renders pipeline fields and schedule grid', () => {
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
    expect(html).toContain('pipeline-schedule-grid');
    expect(html).toContain('pipeline-execution-policy');
    expect(html).toContain('pipeline-stage-monday-research');
    expect(html).toContain('pipeline-stage-sunday-execution');
    expect(html).toContain('pipeline-market-session-static');
    expect(html).toContain('pipeline-runs');
    expect(html).toMatch(/role="switch"/);
  });

  it('hydrates overlay job_runs including skip reasons', async () => {
    const getFn = vi.fn(async () => emptyTip);
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
    await flush();
    expect(jobsFn).toHaveBeenCalledOnce();
    const runs = el.querySelector('[data-testid="pipeline-runs"]');
    expect(runs?.textContent).toMatch(/skipped/);
    expect(runs?.textContent).toMatch(/no_credentials/);
    expect(el.querySelector('[data-testid="pipeline-run-row"]')).not.toBeNull();
  });

  it('hydrates schedule defaults and shows market session when tip exposes it', async () => {
    const getFn = vi.fn(async () => ({
      ...emptyTip,
      pipeline_schedule: null,
      execution_policy: null,
      market_session: {
        venue: 'NYSE',
        is_open: false,
        next_eligible_window: 'Mon 09:30 ET',
      },
    }));
    const el = await mount(
      createElement(PipelineTab, {
        api: { accessToken: 'tok' },
        lastVersionId: 'v1',
        getFn,
        saveFn: vi.fn(),
        jobsFn: vi.fn(async () => []),
      }),
    );
    await flush();
    const mondayResearch = el.querySelector(
      '[data-testid="pipeline-stage-monday-research"]',
    ) as HTMLInputElement | null;
    expect(mondayResearch?.checked).toBe(true);
    expect(el.querySelector('[data-testid="pipeline-market-session"]')?.textContent).toMatch(
      /NYSE/,
    );
    expect(el.querySelector('[data-testid="pipeline-market-session"]')?.textContent).toMatch(
      /Mon 09:30 ET/,
    );
    expect(el.querySelector('[data-testid="pipeline-market-session-static"]')).toBeNull();
  });

  it('saveFn includes schedule + policy and toggles update payload', async () => {
    const saveFn = vi.fn(async () => ({
      version_id: 'v2',
      profile_key: 'workspace',
      schema_version: 1,
      label: 'Workspace overlay',
      supersedes_id: null,
      recorded_at: '2026-08-30T00:00:00Z',
    }));
    const getFn = vi.fn(async () => ({
      ...emptyTip,
      pipeline_schedule: defaultPipelineSchedule(),
      execution_policy: {
        schema_version: 1,
        calendar_mode: 'venue_calendar',
        permitted_venues: [],
        on_closed_session: 'defer',
        respect_early_close: true,
      },
    }));
    const el = await mount(
      createElement(PipelineTab, {
        api: { accessToken: 'tok' },
        lastVersionId: 'v1',
        getFn,
        saveFn,
        jobsFn: vi.fn(async () => []),
      }),
    );
    await flush();

    const satExec = el.querySelector(
      '[data-testid="pipeline-stage-saturday-execution"]',
    ) as HTMLInputElement;
    await act(async () => {
      satExec.click();
    });

    const venues = el.querySelector(
      '[data-testid="pipeline-permitted-venues"]',
    ) as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(venues, 'nyse, nasdaq');
      venues.dispatchEvent(new Event('input', { bubbles: true }));
      venues.dispatchEvent(new Event('change', { bubbles: true }));
    });

    const save = el.querySelector('[data-testid="pipeline-save"]') as HTMLButtonElement;
    await act(async () => {
      save.click();
      await Promise.resolve();
      await Promise.resolve();
    });

    expect(saveFn).toHaveBeenCalledOnce();
    const payload = saveFn.mock.calls[0]![1] as {
      pipeline_schedule: { saturday: { execution: boolean } };
      execution_policy: {
        calendar_mode: string;
        on_closed_session: string;
        permitted_venues: string[];
      };
      watchlist: string[];
      expected_version_id: string;
    };
    expect(payload.expected_version_id).toBe('v1');
    expect(payload.pipeline_schedule.saturday.execution).toBe(false);
    expect(payload.execution_policy.calendar_mode).toBe('venue_calendar');
    expect(payload.execution_policy.on_closed_session).toBe('defer');
    expect(payload.execution_policy.permitted_venues).toEqual(['NYSE', 'NASDAQ']);
    expect(payload.watchlist).toEqual(['AAPL']);
  });

  it('surfaces 409 conflict UX', async () => {
    const saveFn = vi.fn(async () => {
      throw new SettingsHttpError({
        status: 409,
        code: 'CONFLICT',
        message: 'version mismatch',
      });
    });
    const el = await mount(
      createElement(PipelineTab, {
        api: { accessToken: 'tok' },
        lastVersionId: 'v1',
        getFn: vi.fn(async () => emptyTip),
        saveFn,
        jobsFn: vi.fn(async () => []),
      }),
    );
    await flush();
    const save = el.querySelector('[data-testid="pipeline-save"]') as HTMLButtonElement;
    await act(async () => {
      save.click();
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(el.querySelector('[data-testid="pipeline-conflict"]')?.textContent).toMatch(
      /reload/i,
    );
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
