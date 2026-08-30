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
        getFillsFn: vi.fn(async () => []),
        getLogFn: vi.fn(async () => [
          {
            event_key: 'digest:2026-08-31',
            sent_date: '2026-08-31',
            sent_at: '2026-08-31T12:00:00Z',
          },
        ]),
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
  });
});
