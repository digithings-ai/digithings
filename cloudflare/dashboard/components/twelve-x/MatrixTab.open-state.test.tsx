/** @vitest-environment happy-dom */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import MatrixTab from './MatrixTab';
import type { MatrixCell } from '@/lib/twelve-x/types';

/**
 * Positive open-state coverage for the broker-profile slide-over (wave-2 #4206):
 * the panel chrome is a Base UI Sheet portal that never renders under static
 * SSR, so the SSR file can only assert the closed shell. This happy-dom test
 * mounts the tab and drives the real open → close wiring.
 */

// happy-dom does not ship ResizeObserver; Base UI's floating parts probe it.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver ??= RO;

function cell(
  partial: Partial<MatrixCell> & { broker: string; column: MatrixCell['column'] },
): MatrixCell {
  return {
    currency: partial.column,
    direction: 'bullish',
    conviction: 'high',
    run_date: '2026-06-24',
    report_date: null,
    source_file: `${partial.broker}-${partial.column}.md`,
    ...partial,
  };
}

const CELLS: MatrixCell[] = [
  cell({ broker: 'research Macro', column: 'USD', rationale: 'Dollar smile intact' }),
  cell({ broker: 'Meridian FX', column: 'JPY', direction: 'bearish', currency: 'JPY' }),
];

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(createElement(MatrixTab, { cells: CELLS, onOpenBrief: () => {} }));
  });
  return host;
}

afterEach(() => {
  act(() => {
    root?.unmount();
  });
  host?.remove();
  root = null;
  host = null;
});

describe('MatrixTab broker-profile open state (happy-dom)', () => {
  it('opens the slide-over from the desk label, then closes on Escape', async () => {
    const el = await mount();
    // Closed by default: nothing portaled.
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();

    const desk = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('research Macro'),
    );
    expect(desk).toBeTruthy();
    await act(async () => {
      desk!.click();
    });

    const sheet = document.querySelector('[data-slot="sheet-content"]');
    expect(sheet).toBeTruthy();
    expect(sheet?.getAttribute('aria-label')).toBe('Broker profile');
    // The opened panel shows this desk's derived views (the other desk is filtered out).
    expect(sheet?.textContent).toContain('research Macro');
    expect(sheet?.textContent).toContain('Dollar smile intact');
    expect(sheet?.textContent).not.toContain('Meridian FX');

    await act(async () => {
      sheet!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();
  });

  it('seeds the open state from initialSelectedBroker', async () => {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
    await act(async () => {
      root!.render(
        createElement(MatrixTab, {
          cells: CELLS,
          onOpenBrief: () => {},
          initialSelectedBroker: 'Meridian FX',
        }),
      );
    });
    const sheet = document.querySelector('[data-slot="sheet-content"]');
    expect(sheet).toBeTruthy();
    expect(sheet?.textContent).toContain('Meridian FX');
  });
});
