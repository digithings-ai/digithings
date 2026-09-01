/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { RemainingHopStatus } from './remaining-hop-status';

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(ui: React.ReactElement): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(ui);
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
  });
  return host;
}

describe('RemainingHopStatus', () => {
  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  it('marks Observer product state unproven without claiming digest from log', async () => {
    const el = await mount(
      createElement(RemainingHopStatus, {
        api: { accessToken: 'tok' },
        getProfileFn: vi.fn(async () => ({
          version_id: null,
          workspace_id: 'ws',
          profile_key: 'workspace',
          schema_version: 1,
          label: 'Workspace',
          supersedes_id: null,
          recorded_at: null,
          investment: null,
          assets: null,
          plan_tier: 'free',
          subscription_status: 'none',
          has_stripe_subscription: false,
        })),
        listBrokersFn: vi.fn(async () => [
          {
            id: 'c1',
            broker: 'alpaca',
            env: 'paper',
            auth_kind: 'api_key',
            fingerprint: 'abcd',
            status: 'active',
            last_used_at: null,
          },
        ]),
        getJobsFn: vi.fn(async () => []),
        getFillsFn: vi.fn(async () => [
          {
            id: 'f1',
            symbol: 'AAPL',
            quantity: 1,
            executed_at: null,
            recorded_at: null,
          },
        ]),
        getLogFn: vi.fn(async () => [
          {
            event_key: 'digest:2026-08-31',
            sent_date: '2026-08-31',
            sent_at: '2026-08-31T12:00:00Z',
          },
        ]),
        getNotificationsFn: vi.fn(async () => ({
          workspace_id: 'ws',
          email: 'observer@example.com',
          daily_digest: true,
          holding_change_alerts: false,
          execution_alerts: false,
          digest_hour_utc: 13,
          updated_at: '2026-08-31T00:00:00Z',
        })),
      }),
    );
    expect(el.querySelector('[data-testid="remaining-hop-browser_stripe_checkout"]')?.getAttribute('data-proven')).toBe(
      'false',
    );
    expect(
      el.querySelector('[data-testid="remaining-hop-alpaca_paper_oauth_connect"]')?.getAttribute('data-proven'),
    ).toBe('false');
    expect(el.querySelector('[data-testid="remaining-hop-digest_email_received"]')?.getAttribute('data-proven')).toBe(
      'false',
    );
    expect(el.querySelector('[data-testid="remaining-hop-paper_fill_mirrored"]')?.getAttribute('data-proven')).toBe(
      'false',
    );
    expect(
      el.querySelector('[data-testid="remaining-hop-browser_stripe_checkout"]')?.getAttribute('data-blocker'),
    ).toBe('plan_tier_not_custom');
    expect(
      el.querySelector('[data-testid="remaining-hop-alpaca_paper_oauth_connect"]')?.getAttribute('data-blocker'),
    ).toBe('alpaca_api_key_not_oauth');
    expect(
      el.querySelector('[data-testid="remaining-hop-paper_fill_mirrored"]')?.getAttribute('data-blocker'),
    ).toBe('fill_without_oauth');
    expect(
      el.querySelector('[data-testid="remaining-hop-digest_email_received"]')?.getAttribute('data-blocker'),
    ).toBe('digest_inbox_unconfirmed');
    expect(el.textContent).toContain('Custom Stripe checkout required');
    expect(el.textContent).toContain('api_key paper does not prove OAuth');
  });

  it('names leftover UNIQUE overlay failure instead of generic not-succeeded', async () => {
    const el = await mount(
      createElement(RemainingHopStatus, {
        api: { accessToken: 'tok' },
        getProfileFn: vi.fn(async () => ({
          version_id: null,
          workspace_id: 'ws',
          profile_key: 'workspace',
          schema_version: 1,
          label: 'Workspace',
          supersedes_id: null,
          recorded_at: null,
          investment: null,
          assets: null,
          plan_tier: 'custom',
          subscription_status: 'none',
          has_stripe_subscription: false,
        })),
        listBrokersFn: vi.fn(async () => []),
        getJobsFn: vi.fn(async () => [
          {
            id: 'j1',
            job_type: 'overlay_daily',
            status: 'failed',
            error: 'legacy_book_unique',
            idempotency_key: 'k1',
            started_at: null,
            finished_at: null,
          },
        ]),
        getFillsFn: vi.fn(async () => []),
        getLogFn: vi.fn(async () => []),
        getNotificationsFn: vi.fn(async () => ({
          workspace_id: 'ws',
          email: 'observer@example.com',
          daily_digest: true,
          holding_change_alerts: false,
          execution_alerts: false,
          digest_hour_utc: 13,
          updated_at: '2026-08-31T00:00:00Z',
        })),
      }),
    );
    expect(
      el.querySelector('[data-testid="remaining-hop-overlay_daily_claimed"]')?.getAttribute('data-proven'),
    ).toBe('false');
    expect(
      el.querySelector('[data-testid="remaining-hop-overlay_daily_claimed"]')?.getAttribute('data-blocker'),
    ).toBe('overlay_legacy_book_unique');
    expect(el.textContent).toContain('legacy UNIQUE(date) still blocks overlay');
  });
});
