/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { NotifyTab } from './notify-tab';
import { BillingTab } from './billing-tab';
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

describe('NotifyTab', () => {
  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it('hydrates form from GET on mount when api is present', async () => {
    const getFn = vi.fn(async () => ({
      workspace_id: 'ws-a',
      email: 'pm@example.com',
      daily_digest: true,
      holding_change_alerts: false,
      execution_alerts: true,
      digest_hour_utc: 9,
      updated_at: '2026-08-30T00:00:00Z',
    }));
    const patchFn = vi.fn();
    const el = await mount(
      createElement(NotifyTab, {
        api: { accessToken: 'tok' },
        getFn,
        patchFn,
      }),
    );
    await act(async () => {
      await Promise.resolve();
    });
    expect(getFn).toHaveBeenCalledOnce();
    const email = el.querySelector('[data-testid="notify-email"]') as HTMLInputElement;
    const digest = el.querySelector('[data-testid="notify-digest"]') as HTMLInputElement;
    const execution = el.querySelector('[data-testid="notify-execution"]') as HTMLInputElement;
    const hour = el.querySelector('[data-testid="notify-hour"]') as HTMLInputElement;
    expect(email.value).toBe('pm@example.com');
    expect(digest.checked).toBe(true);
    expect(execution.checked).toBe(true);
    expect(hour.value).toBe('9');
    expect(patchFn).not.toHaveBeenCalled();
  });

  it('PATCH round-trip succeeds when function returns ok', async () => {
    const getFn = vi.fn(async () => ({
      workspace_id: 'ws-a',
      email: '',
      daily_digest: false,
      holding_change_alerts: false,
      execution_alerts: false,
      digest_hour_utc: 12,
      updated_at: null,
    }));
    const patchFn = vi.fn(async (_api, payload) => {
      expect(payload.daily_digest).toBe(true);
      expect(payload.email).toBe('pm@example.com');
      return {
        workspace_id: 'ws-a',
        email: 'pm@example.com',
        daily_digest: true,
        holding_change_alerts: false,
        execution_alerts: false,
        digest_hour_utc: 12,
        updated_at: '2026-08-30T12:00:00Z',
      };
    });
    const el = await mount(
      createElement(NotifyTab, {
        api: { accessToken: 'tok' },
        getFn,
        patchFn,
      }),
    );
    await act(async () => {
      await Promise.resolve();
    });
    const email = el.querySelector('[data-testid="notify-email"]') as HTMLInputElement;
    const digest = el.querySelector('[data-testid="notify-digest"]') as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')?.set;
      setter?.call(email, 'pm@example.com');
      email.dispatchEvent(new Event('input', { bubbles: true }));
      digest.click();
    });
    const save = el.querySelector('[data-testid="notify-save"]') as HTMLButtonElement;
    await act(async () => {
      save.click();
    });
    expect(patchFn).toHaveBeenCalledOnce();
    expect(el.querySelector('[data-testid="notify-message"]')?.textContent).toMatch(/saved/i);
  });

  it('surfaces NOT_READY from 503 on save', async () => {
    const getFn = vi.fn(async () => ({
      workspace_id: 'ws-a',
      email: '',
      daily_digest: false,
      holding_change_alerts: false,
      execution_alerts: false,
      digest_hour_utc: 12,
      updated_at: null,
    }));
    const patchFn = vi.fn(async () => {
      throw new SettingsHttpError({
        status: 503,
        code: 'NOT_READY',
        message: 'notification_prefs is not available until K5',
      });
    });
    const el = await mount(
      createElement(NotifyTab, {
        api: { accessToken: 'tok' },
        getFn,
        patchFn,
      }),
    );
    await act(async () => {
      await Promise.resolve();
    });
    const save = el.querySelector('[data-testid="notify-save"]') as HTMLButtonElement;
    await act(async () => {
      save.click();
    });
    expect(el.querySelector('[data-testid="notify-message"]')?.textContent).toMatch(
      /unavailable/i,
    );
  });

  it('skips GET when api is null', () => {
    const getFn = vi.fn();
    const html = renderToStaticMarkup(
      createElement(NotifyTab, { api: null, getFn, patchFn: vi.fn() }),
    );
    expect(html).toContain('settings-notify-tab');
    expect(getFn).not.toHaveBeenCalled();
  });
});

describe('BillingTab', () => {
  it('renders billing not configured when envs absent', () => {
    const html = renderToStaticMarkup(
      createElement(BillingTab, { api: null, configured: false }),
    );
    expect(html).toContain('billing-not-configured');
    expect(html).toContain('Billing is not configured');
  });

  it('links checkout/portal when configured', () => {
    const html = renderToStaticMarkup(
      createElement(BillingTab, {
        api: { accessToken: 'tok' },
        configured: true,
        checkoutFn: vi.fn(),
        portalFn: vi.fn(),
      }),
    );
    expect(html).toContain('billing-checkout-baseline');
    expect(html).toContain('billing-portal');
    expect(html).not.toContain('billing-not-configured');
  });
});
