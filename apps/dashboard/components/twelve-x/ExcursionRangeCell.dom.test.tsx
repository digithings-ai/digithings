/**
 * @vitest-environment happy-dom
 */
import { createElement, act, type ReactElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it } from 'vitest';
import ExcursionRangeCell from './ExcursionRangeCell';

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

describe('ExcursionRangeCell (happy-dom)', () => {
  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it('plots adverse/favorable extremes with the close mark and an sr-only label', async () => {
    const el = await mount(
      createElement(ExcursionRangeCell, {
        maxAdverse: -0.008,
        maxFavorable: 0.02,
        holdReturn: 0.012,
      }),
    );
    const text = el.textContent ?? '';
    expect(text).toContain('-0.8%');
    expect(text).toContain('+2.0%');
    // Spoken label describes observed extremes — never stop/target levels.
    expect(text).toContain('Observed extremes -0.8% to +2.0% vs entry, close mark +1.2%.');
    expect(text).not.toMatch(/stop|target/i);
    // The kit RangeTrack carries the picture and its own spoken summary.
    expect(el.querySelector('[role="img"]')).toBeTruthy();
  });

  it('falls back to an em dash with no excursion data', async () => {
    const el = await mount(
      createElement(ExcursionRangeCell, {
        maxAdverse: null,
        maxFavorable: null,
        holdReturn: 0.012,
      }),
    );
    expect(el.textContent).toBe('—');
  });

  it('omits the marker but keeps the range when the close mark is unknown', async () => {
    const el = await mount(
      createElement(ExcursionRangeCell, {
        maxAdverse: -0.008,
        maxFavorable: 0.02,
        holdReturn: null,
      }),
    );
    const text = el.textContent ?? '';
    expect(text).toContain('no close mark');
    expect(el.textContent).not.toContain('Close mark');
  });
});
