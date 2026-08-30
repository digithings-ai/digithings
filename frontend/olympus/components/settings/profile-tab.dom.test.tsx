/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { ProfileTab } from './profile-tab';
import { SettingsHttpError } from '@/lib/settings-api';

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

describe('ProfileTab (happy-dom)', () => {
  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it('invalid schema shows field error and never calls the network', async () => {
    const saveFn = vi.fn();
    const el = await mount(
      createElement(ProfileTab, {
        api: { accessToken: 'tok' },
        lastVersionId: null,
        saveFn,
      }),
    );
    // Reserved house key is rejected client-side before any network call.
    const keyInput = el.querySelector('[data-testid="profile-key-input"]') as HTMLInputElement;
    expect(keyInput).toBeTruthy();
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(keyInput, 'house');
      keyInput.dispatchEvent(new Event('input', { bubbles: true }));
      keyInput.dispatchEvent(new Event('change', { bubbles: true }));
    });
    const save = el.querySelector('[data-testid="profile-save"]') as HTMLButtonElement;
    await act(async () => {
      save.click();
    });
    expect(saveFn).not.toHaveBeenCalled();
    const err = el.querySelector('[data-testid="profile-field-error"]');
    expect(err?.textContent ?? '').toMatch(/house|reserved/i);
  });

  it('invalid investment enum never reaches saveFn (unit gate)', async () => {
    const { validateInvestmentProfile } = await import('@/lib/settings/validate-profile');
    const saveFn = vi.fn();
    const bad = validateInvestmentProfile({
      risk_tolerance: 'yolo',
      horizon_years: 10,
      liquidity_needs: 'medium',
      base_currency: 'USD',
      tax_jurisdiction: 'US',
      esg_preference: 'none',
      experience_level: 'intermediate',
    });
    expect(bad.ok).toBe(false);
    // Mirror ProfileTab gate: only call network when validation passes.
    if (bad.ok) await saveFn({ accessToken: 'tok' }, {});
    expect(saveFn).not.toHaveBeenCalled();
  });

  it('409 path renders reload copy', async () => {
    const saveFn = vi.fn(async () => {
      throw new SettingsHttpError({
        status: 409,
        code: 'VERSION_CONFLICT',
        message: 'profile changed elsewhere — reload',
      });
    });
    const el = await mount(
      createElement(ProfileTab, {
        api: { accessToken: 'tok' },
        lastVersionId: 'v0',
        saveFn,
      }),
    );
    const save = el.querySelector('[data-testid="profile-save"]') as HTMLButtonElement;
    await act(async () => {
      save.click();
    });
    const conflict = el.querySelector('[data-testid="profile-conflict"]');
    expect(conflict?.textContent ?? '').toMatch(/reload/i);
    expect(saveFn).toHaveBeenCalled();
  });
});
