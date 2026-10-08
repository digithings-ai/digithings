/**
 * @vitest-environment happy-dom
 *
 * The fix series loads in an effect, so the pending state for an unpublishable
 * bracket can only be observed after the fetch resolves (the static-markup test
 * in LevelFixSection.test.tsx stops at the loading state).
 */
import { createElement, act, type ReactElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import type { FxTradeIdeaRow } from '@/lib/twelve-x/types';
import LevelFixSection from './LevelFixSection';
import { getFxFixSeries } from '@/lib/twelve-x/fetch';

vi.mock('@/lib/twelve-x/fetch', () => ({
  getFxFixSeries: vi.fn(),
}));

const mockedFixSeries = vi.mocked(getFxFixSeries);

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(ui: ReactElement): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(ui);
  });
  return host;
}

function idea(tradeLevels: FxTradeIdeaRow['trade_levels']): FxTradeIdeaRow {
  return {
    run_date: '2026-06-12',
    rank: 1,
    pair: 'EUR/USD',
    direction: 'long',
    title: 'EUR/USD long',
    thesis: '',
    catalyst: '',
    levels: [],
    citations: [],
    as_of: '2026-06-26T00:00:00Z',
    trade_levels: tradeLevels,
  };
}

beforeEach(() => {
  mockedFixSeries.mockReset();
});

afterEach(() => {
  act(() => {
    root?.unmount();
  });
  host?.remove();
  root = null;
  host = null;
});

describe('LevelFixSection pending levels (happy-dom)', () => {
  it('renders a pending chart region instead of a half ladder', async () => {
    mockedFixSeries.mockResolvedValue({ 'EUR/USD': [{ date: '2026-06-13', fix: 1.082 }] });
    const el = await mount(
      createElement(LevelFixSection, {
        idea: idea({
          targets: [{ value: '1.1000', provenance: 'broker_quoted', source_ref: 'desk' }],
          status: 'partial',
        }),
      }),
    );
    const text = el.textContent ?? '';
    expect(text).toContain('Levels pending');
    // The partial target must not be drawn as a published level.
    expect(el.querySelector('[data-testid="level-fix-chart"]')).toBeNull();
    // No internal enum in rendered markup.
    expect(text).not.toMatch(/partial|incomplete/i);
  });

  it('renders the chart with levels for a complete bracket', async () => {
    mockedFixSeries.mockResolvedValue({ 'EUR/USD': [{ date: '2026-06-13', fix: 1.082 }] });
    const el = await mount(
      createElement(LevelFixSection, {
        idea: idea({
          entry_low: { value: '1.0800', provenance: 'broker_quoted', source_ref: 'desk' },
          entry_high: { value: '1.0850', provenance: 'broker_quoted', source_ref: 'desk' },
          stop: { value: '1.0700', provenance: 'broker_quoted', source_ref: 'desk' },
          targets: [{ value: '1.1000', provenance: 'broker_quoted', source_ref: 'desk' }],
          status: 'complete',
        }),
      }),
    );
    expect(el.querySelector('[data-testid="level-fix-chart"]')).not.toBeNull();
    expect(el.textContent ?? '').not.toContain('Levels pending');
  });
});