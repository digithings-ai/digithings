/** @vitest-environment happy-dom */
import { afterEach, describe, expect, it, vi } from 'vitest';
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';

import TradesTab from './TradesTab';
import type { FxIdeaEvalRow, FxTradeIdeaRow } from '@/lib/twelve-x/types';

// happy-dom does not ship IntersectionObserver; the table's scroll sentinel
// only needs the interface to exist.
class IO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { IntersectionObserver?: unknown }).IntersectionObserver ??= IO;

const idea: FxTradeIdeaRow = {
  run_date: '2026-07-24',
  rank: 1,
  pair: 'USD/JPY',
  direction: 'long',
  title: 'USD/JPY long',
  thesis: 'thesis',
  catalyst: 'data',
  levels: [],
  citations: [],
  as_of: '2026-07-24T00:00:00Z',
};

const evalRow: FxIdeaEvalRow = {
  run_date: '2026-07-24',
  rank: 1,
  horizon_days: 0,
  pair: 'USD/JPY',
  direction: 'long',
  status: 'resolved',
  entry_date: '2026-07-24',
  exit_date: '2026-07-29',
  entry_fix: 148,
  exit_fix: 149,
  ret: 0.012,
  hold_return: 0.012,
  sigma_entry: 0.004,
  hit: true,
  directional_win: true,
  significant_hit: true,
  n_sessions: 5,
  as_of: '2026-07-29T00:00:00Z',
  outcome: 'right',
  grade_basis: 'measured',
  closed_by: 'successor',
};

let host: HTMLDivElement | null = null;
let root: Root | null = null;

afterEach(() => {
  act(() => {
    root?.unmount();
  });
  host?.remove();
  root = null;
  host = null;
});

async function mount() {
  const onOpenIdea = vi.fn();
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(
      createElement(TradesTab, { ideas: [idea], ideaEval: [evalRow], onOpenIdea }),
    );
  });
  return onOpenIdea;
}

describe('TradesTab row interaction', () => {
  function row(): HTMLElement {
    const el = document.querySelector('tbody tr[tabindex="0"]');
    expect(el).not.toBeNull();
    return el as HTMLElement;
  }

  it('opens the idea sidebar when a row is clicked', async () => {
    const onOpenIdea = await mount();
    await act(async () => {
      row().click();
    });
    expect(onOpenIdea).toHaveBeenCalledWith('2026-07-24', 1);
  });

  it('opens the idea sidebar when Enter is pressed on a row', async () => {
    const onOpenIdea = await mount();
    await act(async () => {
      row().dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
    });
    expect(onOpenIdea).toHaveBeenCalledWith('2026-07-24', 1);
  });

  it('opens the idea sidebar when Space is pressed on a row', async () => {
    const onOpenIdea = await mount();
    await act(async () => {
      row().dispatchEvent(new KeyboardEvent('keydown', { key: ' ', bubbles: true }));
    });
    expect(onOpenIdea).toHaveBeenCalledWith('2026-07-24', 1);
  });
});
