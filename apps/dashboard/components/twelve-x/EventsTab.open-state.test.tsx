/** @vitest-environment happy-dom */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import EventsTab, { eventById } from './EventsTab';
import type { FxEconomicCalendarRow, FxEventSnapshotRow } from '@/lib/twelve-x/types';

/**
 * Positive open-state coverage for the event-detail slide-over (wave-2 #4206):
 * the panel chrome is a Base UI Sheet portal that never renders under static
 * SSR, so the SSR file can only assert the closed shell. These tests cover the
 * open-state derivation (`eventById`), the seed wiring, the row-click wiring,
 * and the Escape close — all deterministic, no network.
 */

// happy-dom does not ship ResizeObserver; Base UI's floating parts probe it.
class RO {
  observe() {}
  unobserve() {}
  disconnect() {}
}
(globalThis as unknown as { ResizeObserver?: unknown }).ResizeObserver ??= RO;

const EVENTS: FxEconomicCalendarRow[] = [
  {
    id: 1,
    external_id: 'pce-1',
    event_date: '2026-06-22',
    event_time: '12:30',
    country: 'US',
    event_name: 'Core PCE Price Index',
    category: 'macro',
    impact: 'high',
    prior: '2.7%',
    forecast: '2.6%',
    actual: null,
    event_datetime_utc: '2026-06-22T12:30:00Z',
  },
  {
    id: 2,
    external_id: 'ecb-2',
    event_date: '2026-06-22',
    event_time: '14:00',
    country: 'EU',
    event_name: 'ECB President Speech',
    category: 'macro',
    impact: 'medium',
    prior: null,
    forecast: null,
    actual: null,
    event_datetime_utc: '2026-06-22T14:00:00Z',
  },
];

const OPINIONS: FxEventSnapshotRow[] = [
  {
    run_date: '2026-06-22',
    event_key: 'core-pce',
    event_name: 'Core PCE Price Index',
    event_date: null,
    calendar_external_id: 'pce-1',
    release_at: null,
    category: 'macro',
    currencies: [],
    mentions: 2,
    brokers: ['research Macro'],
    citations: [],
    as_of: '2026-06-22T00:00:00Z',
  },
];

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(props: { initialSelectedId?: string | null } = {}): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(
      createElement(EventsTab, {
        events: EVENTS,
        opinions: OPINIONS,
        runDate: '2026-06-22',
        focus: null,
        ...props,
      }),
    );
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

describe('eventById (slide-over open-state derivation)', () => {
  it('resolves a targeted id to its event row (open state)', () => {
    expect(eventById(EVENTS, '1')?.event_name).toBe('Core PCE Price Index');
    expect(eventById(EVENTS, 2)?.event_name).toBe('ECB President Speech');
  });

  it('returns null for absent/unknown ids (closed state)', () => {
    expect(eventById(EVENTS, null)).toBeNull();
    expect(eventById(EVENTS, undefined)).toBeNull();
    expect(eventById(EVENTS, '')).toBeNull();
    expect(eventById(EVENTS, 'nope')).toBeNull();
  });
});

describe('EventsTab event-detail open state (happy-dom)', () => {
  it('seeds the open slide-over from initialSelectedId, then closes on Escape', async () => {
    await mount({ initialSelectedId: '1' });
    const sheet = document.querySelector('[data-slot="sheet-content"]');
    expect(sheet).toBeTruthy();
    expect(sheet?.getAttribute('aria-label')).toBe('Event detail');
    expect(sheet?.textContent).toContain('Core PCE Price Index');

    await act(async () => {
      sheet!.dispatchEvent(new KeyboardEvent('keydown', { key: 'Escape', bubbles: true }));
      await new Promise((r) => setTimeout(r, 50));
    });
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();
  });

  it('opens the slide-over from an evidence-bearing row click', async () => {
    const el = await mount();
    expect(document.querySelector('[data-slot="sheet-content"]')).toBeNull();

    const row = Array.from(el.querySelectorAll('button')).find((b) =>
      b.textContent?.includes('Core PCE Price Index'),
    );
    expect(row).toBeTruthy();
    await act(async () => {
      row!.click();
    });

    const sheet = document.querySelector('[data-slot="sheet-content"]');
    expect(sheet).toBeTruthy();
    expect(sheet?.textContent).toContain('Core PCE Price Index');
    expect(sheet?.textContent).toContain('2 mentions');
  });
});
