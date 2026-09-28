/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { KeysTab } from './keys-tab';
import { SETTINGS_LOAD_ERROR_MESSAGE } from './settings-load-error';

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(ui: React.ReactElement): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(ui);
  });
  // Allow hydrate microtasks to settle
  await act(async () => {
    await Promise.resolve();
  });
  return host;
}

describe('KeysTab hydrate load error (happy-dom)', () => {
  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it('shows shared SettingsLoadError and Retry re-triggers listFn', async () => {
    const listFn = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce([]);
    const el = await mount(
      createElement(KeysTab, {
        api: { accessToken: 'tok' },
        listFn,
        connectFn: vi.fn(),
        revokeFn: vi.fn(),
      }),
    );

    expect(listFn).toHaveBeenCalledTimes(1);
    const shell = el.querySelector('[data-testid="settings-load-error"]');
    expect(shell?.textContent ?? '').toContain(SETTINGS_LOAD_ERROR_MESSAGE);
    expect(shell?.textContent ?? '').not.toMatch(/Unable to load keys/i);

    const retry = el.querySelector(
      '[data-testid="settings-load-error-retry"]',
    ) as HTMLButtonElement;
    expect(retry).toBeTruthy();
    await act(async () => {
      retry.click();
      await Promise.resolve();
    });
    expect(listFn).toHaveBeenCalledTimes(2);
  });
});
