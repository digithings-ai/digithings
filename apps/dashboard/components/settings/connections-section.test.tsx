/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import type { SettingsTabId } from '@/lib/entitlements';
import { ConnectionsSection, type ConnectionsSectionProps } from './connections-section';
import { SETTINGS_LOAD_ERROR_MESSAGE } from './settings-load-error';

const ALL_TABS: SettingsTabId[] = ['brokers', 'keys'];
const API = { accessToken: 'tok' };
const URLS = {
  alpaca_redirect_uri: 'x',
  billing_return_url: 'y',
  alpaca_oauth_client_id: 'cid-from-ef',
};

let root: Root | null = null;
let host: HTMLElement | null = null;

async function mount(props: Partial<ConnectionsSectionProps> = {}): Promise<HTMLElement> {
  host = document.createElement('div');
  document.body.appendChild(host);
  root = createRoot(host);
  await act(async () => {
    root!.render(
      createElement(ConnectionsSection, {
        api: API,
        visibleTabs: ALL_TABS,
        listBrokersFn: vi.fn(async () => []),
        listKeysFn: vi.fn(async () => []),
        connectBrokerFn: vi.fn(),
        connectKeyFn: vi.fn(),
        revokeBrokerFn: vi.fn(),
        revokeKeyFn: vi.fn(),
        fillsFn: vi.fn(async () => []),
        appUrlsFn: vi.fn(async () => URLS),
        ...props,
      }),
    );
  });
  await act(async () => {
    await Promise.resolve();
    await Promise.resolve();
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

const click = async (el: Element | null) => {
  await act(async () => {
    (el as HTMLElement).click();
  });
};

const brokerRow = (over: Record<string, unknown> = {}) => ({
  id: 'b1',
  broker: 'alpaca',
  env: 'paper',
  auth_kind: 'oauth',
  fingerprint: 'face0001',
  status: 'active',
  last_used_at: null,
  ...over,
});
const keyRow = (over: Record<string, unknown> = {}) => ({
  id: 'k1',
  provider: 'openai',
  fingerprint: 'abcd1234',
  status: 'active',
  last_used_at: null,
  ...over,
});

describe('ConnectionsSection merged table', () => {
  it('renders brokers and model keys in one table with status and fingerprint', async () => {
    const el = await mount({
      listBrokersFn: vi.fn(async () => [brokerRow()] as never),
      listKeysFn: vi.fn(async () => [keyRow()] as never),
    });
    expect(el.querySelectorAll('table')).toHaveLength(1);
    const b = el.querySelector('[data-testid="broker-row"]');
    const k = el.querySelector('[data-testid="keys-row"]');
    expect(b?.textContent).toContain('face0001');
    expect(b?.textContent).toContain('paper');
    expect(k?.textContent).toContain('OpenAI');
    expect(el.querySelector('[data-testid="connections-summary"]')?.textContent).toBe(
      '2 connections, 2 active',
    );
  });

  it('never renders secret fields that leak onto listed rows', async () => {
    const el = await mount({
      listBrokersFn: vi.fn(async () => [brokerRow({ secret: 'LEAK-A', ciphertext: 'LEAK-B' })] as never),
      listKeysFn: vi.fn(async () => [keyRow({ secret: 'LEAK-C', api_key: 'LEAK-D' })] as never),
    });
    expect(el.textContent).not.toMatch(/LEAK/);
    expect(el.innerHTML).not.toMatch(/LEAK/);
  });

  it('shows Revoke only on active rows', async () => {
    const el = await mount({
      listBrokersFn: vi.fn(async () => [brokerRow(), brokerRow({ id: 'b2', status: 'revoked' })] as never),
      listKeysFn: vi.fn(async () => [keyRow({ status: 'revoked' })] as never),
    });
    expect(el.querySelectorAll('[data-testid="broker-revoke"]')).toHaveLength(1);
    expect(el.querySelectorAll('[data-testid="keys-revoke"]')).toHaveLength(0);
  });

  it('revoking a broker calls the broker revoke with connection_id and flips the row', async () => {
    const revokeBrokerFn = vi.fn(async () => brokerRow({ status: 'revoked' }) as never);
    const el = await mount({
      listBrokersFn: vi.fn(async () => [brokerRow()] as never),
      revokeBrokerFn,
    });
    await click(el.querySelector('[data-testid="broker-revoke"]'));
    expect(revokeBrokerFn).toHaveBeenCalledWith(API, { connection_id: 'b1' });
    expect(el.querySelector('[data-testid="broker-revoke"]')).toBeNull();
    expect(el.querySelector('[data-testid="broker-row"]')?.getAttribute('data-status')).toBe('revoked');
  });

  it('revoking a model key uses credential_id', async () => {
    const revokeKeyFn = vi.fn(async () => keyRow({ status: 'revoked' }) as never);
    const el = await mount({
      listKeysFn: vi.fn(async () => [keyRow()] as never),
      revokeKeyFn,
    });
    await click(el.querySelector('[data-testid="keys-revoke"]'));
    expect(revokeKeyFn).toHaveBeenCalledWith(API, { credential_id: 'k1' });
  });

  it('empty state offers the add flow', async () => {
    const el = await mount();
    expect(el.textContent).toContain('No connections yet');
    expect(el.querySelector('table')).toBeNull();
  });
});

describe('ConnectionsSection gating', () => {
  it('Desk (brokers only) never loads or offers model keys', async () => {
    const listKeysFn = vi.fn(async () => []);
    const el = await mount({ visibleTabs: ['brokers'], listKeysFn });
    expect(listKeysFn).not.toHaveBeenCalled();
    await click(el.querySelector('[data-testid="connections-add"]'));
    expect(el.textContent).not.toContain('Model key');
    expect(el.querySelector('[data-testid="alpaca-oauth-connect"]')).not.toBeNull();
  });
});

describe('ConnectionsSection credential entry', () => {
  it('saves a broker API key, clears the inputs, and shows the new row without the secret', async () => {
    const secret = 'PLAINTEXT-MUST-DIE';
    const connectBrokerFn = vi.fn(async () => brokerRow({ id: 'c1', fingerprint: 'deadbeef', auth_kind: 'api_key' }) as never);
    const el = await mount({ connectBrokerFn });
    await click(el.querySelector('[data-testid="connections-add"]'));
    // segment 1 = Broker API key
    await click(el.querySelectorAll('[data-testid="connections-add-panel"] button')[1] ?? null);
    const setValue = async (testid: string, value: string) => {
      const input = el.querySelector(`[data-testid="${testid}"]`) as HTMLInputElement;
      await act(async () => {
        const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
        setter.call(input, value);
        input.dispatchEvent(new Event('input', { bubbles: true }));
      });
    };
    await setValue('broker-key-id', 'PK123');
    await setValue('broker-secret', secret);
    await click(el.querySelector('[data-testid="broker-api-key-connect"]'));
    expect(connectBrokerFn).toHaveBeenCalledWith(API, { broker: 'alpaca', key_id: 'PK123', secret });
    expect((el.querySelector('[data-testid="broker-secret"]') as HTMLInputElement).value).toBe('');
    expect((el.querySelector('[data-testid="broker-key-id"]') as HTMLInputElement).value).toBe('');
    expect(el.innerHTML).not.toContain(secret);
    expect(el.querySelector('[data-testid="broker-row"]')?.textContent).toContain('deadbeef');
  });

  it('starts Alpaca OAuth with the public client id and env=paper, no secret in the URL', async () => {
    const navigated: string[] = [];
    const appUrlsFn = vi.fn(async () => URLS);
    const el = await mount({ appUrlsFn, onAuthorizeNavigate: (u) => navigated.push(u) });
    expect(appUrlsFn).toHaveBeenCalledOnce();
    await click(el.querySelector('[data-testid="connections-add"]'));
    await click(el.querySelector('[data-testid="alpaca-oauth-connect"]'));
    expect(navigated).toHaveLength(1);
    const u = new URL(navigated[0]!);
    expect(u.searchParams.get('client_id')).toBe('cid-from-ef');
    expect(u.searchParams.get('env')).toBe('paper');
    expect(navigated[0]).not.toMatch(/secret/i);
  });

  it('unauthenticated add is blocked with a sign-in message', async () => {
    const el = await mount({ api: null });
    await click(el.querySelector('[data-testid="connections-add"]'));
    await click(el.querySelectorAll('[data-testid="connections-add-panel"] button')[2] ?? null);
    const input = el.querySelector('[data-testid="keys-secret"]') as HTMLInputElement;
    await act(async () => {
      const setter = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      setter.call(input, 'sk-x');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    await click(el.querySelector('[data-testid="keys-connect"]'));
    expect(el.querySelector('[data-testid="brokers-error"]')?.textContent).toContain('Sign in');
  });
});

describe('ConnectionsSection paper fills', () => {
  it('hydrates fills into a table', async () => {
    const fillsFn = vi.fn(async () => [
      { id: 'f1', symbol: 'AAPL', quantity: 1, executed_at: '2026-08-31T14:00:00Z', recorded_at: null },
    ]);
    const el = await mount({ fillsFn });
    expect(fillsFn).toHaveBeenCalledOnce();
    expect(el.querySelector('[data-testid="broker-fill-row"]')?.textContent).toMatch(/AAPL/);
  });
});

describe('ConnectionsSection load error', () => {
  it('shows the shared error shell and Retry re-lists', async () => {
    const listBrokersFn = vi
      .fn()
      .mockRejectedValueOnce(new Error('network down'))
      .mockResolvedValueOnce([]);
    const el = await mount({ listBrokersFn });
    expect(el.querySelector('[data-testid="settings-load-error"]')?.textContent).toContain(
      SETTINGS_LOAD_ERROR_MESSAGE,
    );
    await click(el.querySelector('[data-testid="settings-load-error-retry"]'));
    expect(listBrokersFn).toHaveBeenCalledTimes(2);
  });
});

describe('ConnectionsSection SSR', () => {
  it('prerenders anchors for #brokers and #keys without any secret', () => {
    const html = renderToStaticMarkup(
      createElement(ConnectionsSection, { api: null, visibleTabs: ALL_TABS }),
    );
    expect(html).toContain('id="brokers"');
    expect(html).toContain('id="keys"');
    expect(html).not.toMatch(/sk-|secret":/);
  });
});
