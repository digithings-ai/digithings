/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const h = vi.hoisted(() => ({
  configured: true,
  date: '2026-01-01' as string | null,
  pipelineId: 'baseline',
  dates: { data: [{ date: '2026-01-01' }] as { date: string }[] | null, error: null as unknown },
  docs: { data: [{ document_key: 'macro' }] as { document_key: string }[] | null, error: null as unknown },
  throwOnRead: false,
  scopes: [] as string[],
}));

vi.mock('next/navigation', () => ({
  useSearchParams: () => new URLSearchParams(h.date ? `date=${h.date}` : ''),
}));
vi.mock('@/components/pipeline-selection', () => ({
  usePipelineSelection: () => ({ pipelineId: h.pipelineId, scope: { pipelineId: h.pipelineId } }),
}));
vi.mock('@/lib/api-client', () => ({ isApiConfigured: () => h.configured }));
vi.mock('@/lib/pipeline-scope', () => ({
  applyPipelineScope: (q: unknown, _t: string, scope: { pipelineId: string }) => {
    h.scopes.push(scope.pipelineId);
    return q;
  },
}));
vi.mock('@/lib/api-query', () => {
  const result = (table: string) => (table === 'daily_snapshots' ? h.dates : h.docs);
  return {
    apiDb: {
      from: (table: string) => {
        const q: Record<string, unknown> = {};
        const self = () => q;
        q.select = self;
        q.gte = self;
        q.order = self;
        q.eq = self;
        q.then = (ok: (v: unknown) => unknown, bad: (e: unknown) => unknown) => {
          if (h.throwOnRead) return Promise.reject(new Error('boom')).then(ok, bad);
          return Promise.resolve(result(table)).then(ok, bad);
        };
        return q;
      },
    },
  };
});
vi.mock('./use-run-diagnostics', () => ({
  useRunDiagnostics: () => ({ diagnostics: [], loading: false, unavailable: false }),
}));

// Panels are stubbed: the test is about PipelineClient's own state machine.
vi.mock('./PipelineDaySelector', () => ({ default: () => null }));
vi.mock('./PipelineRunStrip', () => ({ default: () => null }));
vi.mock('./PipelineRunHealth', () => ({ default: () => null }));
vi.mock('./PipelineCanvas', () => ({
  default: (p: { day: { runRecorded?: boolean }; onNodeActivate: (n: unknown) => void }) =>
    createElement(
      'button',
      {
        type: 'button',
        'data-testid': 'canvas',
        'data-run-recorded': String(p.day.runRecorded),
        onClick: () => p.onNodeActivate({ id: 'n1', documentKey: 'macro' }),
      },
      'canvas',
    ),
}));
vi.mock('./PipelineNodeDetail', () => ({ default: () => createElement('div', { 'data-testid': 'detail' }) }));
vi.mock('./PipelineArtifactLedger', () => ({ default: () => createElement('div', { 'data-testid': 'artifact-ledger' }) }));
vi.mock('./PipelineTraceLedger', () => ({ default: () => createElement('div', { 'data-testid': 'trace-ledger' }) }));
vi.mock('./PipelineTimeline', () => ({
  default: (p: { onSelectKey: (k: string) => void }) =>
    createElement('button', { type: 'button', 'data-testid': 'timeline', onClick: () => p.onSelectKey('sector-tech') }, 'timeline'),
}));

import PipelineClient from './PipelineClient';

describe('PipelineClient', () => {
  let container: HTMLDivElement;
  let root: Root;
  const q = (id: string) => container.querySelector(`[data-testid="${id}"]`);
  const btn = (label: string) => container.querySelector(`button[aria-label="${label}"]`) as HTMLButtonElement;

  async function mount() {
    await act(async () => {
      root.render(createElement(PipelineClient));
    });
    await act(async () => {});
  }
  const click = async (el: Element | null) => {
    await act(async () => {
      (el as HTMLElement).click();
    });
  };

  beforeEach(() => {
    h.configured = true;
    h.date = '2026-01-01';
    h.pipelineId = 'baseline';
    h.dates = { data: [{ date: '2026-01-01' }], error: null };
    h.docs = { data: [{ document_key: 'macro' }], error: null };
    h.throwOnRead = false;
    h.scopes = [];
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });
  afterEach(() => {
    act(() => root.unmount());
    container.remove();
  });

  it('ready run: no banners and the canvas is told a run is recorded', async () => {
    await mount();
    expect(q('pipeline-data-unavailable')).toBeNull();
    expect(container.textContent).not.toContain('No run recorded');
    expect(q('canvas')?.getAttribute('data-run-recorded')).toBe('true');
  });

  it('not-configured: says the API is not configured, not "no run"', async () => {
    h.configured = false;
    await mount();
    expect(q('pipeline-data-unavailable')?.textContent).toContain('API not configured');
    expect(container.textContent).not.toContain('No run recorded');
    expect(q('canvas')?.getAttribute('data-run-recorded')).toBe('false');
  });

  it('unavailable: a read error is an outage, not an empty pipeline', async () => {
    h.docs = { data: null, error: { message: 'down' } };
    await mount();
    expect(q('pipeline-data-unavailable')?.textContent).toContain('Run data unavailable');
    expect(container.textContent).not.toContain('No run recorded');
  });

  it('unavailable: a thrown read is also an outage', async () => {
    h.throwOnRead = true;
    await mount();
    expect(q('pipeline-data-unavailable')?.textContent).toContain('Run data unavailable');
  });

  it('no-run: a healthy read with no snapshot for the date says "No run recorded"', async () => {
    h.dates = { data: [{ date: '2026-02-02' }], error: null };
    h.docs = { data: [], error: null };
    await mount();
    expect(container.textContent).toContain('No run recorded');
    expect(q('pipeline-data-unavailable')).toBeNull();
    expect(q('canvas')?.getAttribute('data-run-recorded')).toBe('false');
  });

  it('right pane is exclusive: detail, artifact ledger and trace ledger replace one another', async () => {
    await mount();
    await click(q('canvas'));
    expect(q('detail')).not.toBeNull();

    await click(btn('Open all pipeline artifacts'));
    expect(q('artifact-ledger')).not.toBeNull();
    expect(q('detail')).toBeNull();

    await click(btn('Open pipeline call trace'));
    expect(q('trace-ledger')).not.toBeNull();
    expect(q('artifact-ledger')).toBeNull();
    expect(q('detail')).toBeNull();
  });

  it('timeline toggles independently and selecting a key closes ledgers and opens detail', async () => {
    await mount();
    expect(q('timeline')).toBeNull();
    await click(btn('Open all pipeline artifacts'));
    await click(btn('Toggle run timeline'));
    expect(q('timeline')).not.toBeNull();
    expect(btn('Toggle run timeline').getAttribute('aria-pressed')).toBe('true');
    expect(q('artifact-ledger')).not.toBeNull(); // opening the timeline does not close the ledger

    await click(q('timeline'));
    expect(q('artifact-ledger')).toBeNull();
    expect(q('detail')).not.toBeNull();

    await click(btn('Toggle run timeline'));
    expect(q('timeline')).toBeNull();
  });

  it('switching pipeline re-keys the surface: panels reset and reads use the new scope', async () => {
    await mount();
    await click(q('canvas'));
    await click(btn('Toggle run timeline'));
    expect(q('detail')).not.toBeNull();
    expect(q('timeline')).not.toBeNull();
    expect(new Set(h.scopes)).toEqual(new Set(['baseline']));

    h.pipelineId = 'alt';
    await mount();
    expect(q('detail')).toBeNull();
    expect(q('timeline')).toBeNull();
    expect(btn('Toggle run timeline').getAttribute('aria-pressed')).toBe('false');
    expect(h.scopes).toContain('alt');
  });
});
