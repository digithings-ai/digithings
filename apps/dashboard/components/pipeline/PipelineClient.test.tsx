/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const search = vi.hoisted(() => new URLSearchParams('date=2026-09-01'));

vi.mock('next/navigation', () => ({
  useSearchParams: () => search,
}));

vi.mock('@/lib/api-client', () => ({
  isApiConfigured: () => true,
}));

const docsByDate = vi.hoisted(() => new Map<string, { data: unknown; error: unknown } | Error>());

vi.mock('@/lib/api-query', () => ({
  apiDb: {
    from(table: string) {
      const filters: { column: string; value: unknown }[] = [];
      const builder: Record<string, unknown> = {
        select() {
          return builder;
        },
        gte() {
          return builder;
        },
        order() {
          return builder;
        },
        eq(column: string, value: unknown) {
          filters.push({ column, value });
          return builder;
        },
        then(resolve: (value: unknown) => void, reject?: (reason: unknown) => void) {
          if (table === 'daily_snapshots') {
            resolve({
              data: [{ date: '2026-09-02' }, { date: '2026-09-01' }],
              error: null,
            });
            return;
          }
          const date = String(filters.find((filter) => filter.column === 'date')?.value ?? '');
          const result = docsByDate.get(date);
          if (result instanceof Error) {
            reject?.(result);
            return;
          }
          resolve(result ?? { data: [], error: null });
        },
      };
      return builder;
    },
  },
}));

vi.mock('./PipelineCanvas', () => ({
  default: (props: { day: { artifacts: { title: string | null }[] } }) =>
    createElement(
      'div',
      { 'data-testid': 'pipeline-canvas' },
      props.day.artifacts.map((artifact) => artifact.title ?? '').join('|'),
    ),
}));

vi.mock('./PipelineRunHealth', () => ({
  default: (props: { date: string }) =>
    createElement('div', { 'data-testid': 'pipeline-date' }, props.date),
}));

vi.mock('./PipelineDaySelector', () => ({
  default: (props: { value: string; onChange: (date: string) => void }) =>
    createElement(
      'button',
      {
        type: 'button',
        'data-testid': 'pipeline-pick-date',
        onClick: () => props.onChange('2026-09-02'),
      },
      props.value,
    ),
}));

vi.mock('./PipelineNodeDetail', () => ({ default: () => null }));
vi.mock('./PipelineArtifactLedger', () => ({ default: () => null }));
vi.mock('./PipelineTraceLedger', () => ({ default: () => null }));

import PipelineClient from './PipelineClient';

const MONDAY = {
  document_key: 'digest',
  title: 'Monday book',
  doc_type: null,
  phase: null,
  category: null,
  segment: null,
  sector: null,
  run_type: null,
};

describe('PipelineClient', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    search.set('date', '2026-09-01');
    docsByDate.clear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  async function renderClient(): Promise<void> {
    await act(async () => {
      root.render(createElement(PipelineClient));
    });
  }

  async function pickLaterDate(): Promise<void> {
    await act(async () => {
      container.querySelector<HTMLButtonElement>('[data-testid="pipeline-pick-date"]')?.click();
    });
  }

  it('clears the previous day when a later date read returns no documents', async () => {
    docsByDate.set('2026-09-01', { data: [MONDAY], error: null });
    docsByDate.set('2026-09-02', { data: null, error: { message: 'documents down' } });
    await renderClient();
    expect(container.querySelector('[data-testid="pipeline-canvas"]')?.textContent).toBe(
      'Monday book',
    );
    expect(container.querySelector('[data-testid="pipeline-date"]')?.textContent).toBe('2026-09-01');

    await pickLaterDate();

    expect(container.querySelector('[data-testid="pipeline-date"]')?.textContent).toBe('2026-09-02');
    expect(container.querySelector('[data-testid="pipeline-canvas"]')?.textContent).toBe('');
  });

  it('clears the previous day when a later date read throws', async () => {
    docsByDate.set('2026-09-01', { data: [MONDAY], error: null });
    docsByDate.set('2026-09-02', new Error('documents down'));
    await renderClient();
    expect(container.querySelector('[data-testid="pipeline-canvas"]')?.textContent).toBe(
      'Monday book',
    );

    await pickLaterDate();

    expect(container.querySelector('[data-testid="pipeline-date"]')?.textContent).toBe('2026-09-02');
    expect(container.querySelector('[data-testid="pipeline-canvas"]')?.textContent).toBe('');
  });
});
