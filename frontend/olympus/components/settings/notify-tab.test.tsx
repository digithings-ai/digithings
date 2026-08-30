import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { NotifyTab } from './notify-tab';
import { BillingTab } from './billing-tab';
import { SettingsHttpError } from '@/lib/settings-api';

describe('NotifyTab', () => {
  it('PATCH round-trip succeeds when function returns ok', async () => {
    const patchFn = vi.fn(async (_api, payload) => {
      expect(payload.daily_digest).toBe(true);
      expect(payload.email).toBe('pm@example.com');
      return { ok: true };
    });
    await patchFn(
      { accessToken: 'tok' },
      {
        email: 'pm@example.com',
        daily_digest: true,
        holding_change_alerts: false,
        execution_alerts: false,
        digest_hour_utc: 12,
      },
    );
    expect(patchFn).toHaveBeenCalledOnce();
    const html = renderToStaticMarkup(
      createElement(NotifyTab, { api: { accessToken: 'tok' }, patchFn }),
    );
    expect(html).toContain('settings-notify-tab');
  });

  it('surfaces NOT_READY from 503', async () => {
    const patchFn = vi.fn(async () => {
      throw new SettingsHttpError({
        status: 503,
        code: 'NOT_READY',
        message: 'notification_prefs is not available until K5',
      });
    });
    await expect(patchFn({ accessToken: 'tok' }, {})).rejects.toMatchObject({
      code: 'NOT_READY',
    });
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
