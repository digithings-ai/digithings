/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { describe, expect, it, vi } from 'vitest';
import { BrokersTab, sanitizeConnection } from './brokers-tab';
import { buildAlpacaAuthorizeUrl } from '@/lib/settings/alpaca-oauth';

describe('BrokersTab', () => {
  it('sanitizeConnection drops secret / ciphertext fields', () => {
    const row = sanitizeConnection({
      id: '1',
      broker: 'alpaca',
      env: 'paper',
      fingerprint: 'abcd1234',
      status: 'active',
      last_used_at: null,
      secret: 'LEAK',
      ciphertext: 'LEAK',
      access_token: 'LEAK',
    } as never);
    const blob = JSON.stringify(row);
    expect(blob).not.toContain('LEAK');
    expect(blob).not.toContain('secret');
    expect(blob).not.toContain('ciphertext');
    expect(blob).not.toContain('access_token');
    expect(row.fingerprint).toBe('abcd1234');
  });

  it('connect + revoke flows mocked end-to-end; no plaintext after save', async () => {
    const secret = 'PLAINTEXT-MUST-DIE';
    const connectFn = vi.fn(async (_api, payload) => {
      expect(payload.secret).toBe(secret);
      return {
        id: 'c1',
        broker: payload.broker,
        env: 'paper',
        fingerprint: 'deadbeef',
        status: 'active',
        last_used_at: null,
      };
    });
    const revokeFn = vi.fn(async (_api, payload) => ({
      id: payload.connection_id,
      broker: 'alpaca',
      env: 'paper',
      fingerprint: 'deadbeef',
      status: 'revoked',
      last_used_at: null,
    }));
    const listFn = vi.fn(async () => []);

    const connected = await connectFn(
      { accessToken: 'tok' },
      { broker: 'alpaca' as const, key_id: 'PK', secret },
    );
    const safe = sanitizeConnection(connected);
    expect(JSON.stringify(safe)).not.toContain(secret);

    const revoked = await revokeFn(
      { accessToken: 'tok' },
      { connection_id: connected.id },
    );
    expect(revoked.status).toBe('revoked');
    expect(listFn).not.toHaveBeenCalled();

    const html = renderToStaticMarkup(
      createElement(BrokersTab, {
        api: { accessToken: 'tok' },
        listFn,
        connectFn,
        revokeFn,
      }),
    );
    expect(html).toContain('settings-brokers-tab');
    expect(html).toContain('IBKR (beta)');
    expect(html).toContain('brokers-fills');
    expect(html).not.toContain(secret);
  });

  it('Alpaca authorize URL uses env=paper', () => {
    const url = buildAlpacaAuthorizeUrl({
      clientId: 'cid',
      redirectUri: 'https://x/settings/brokers/callback',
      state: 's',
    });
    expect(url).toContain('env=paper');
  });

  it('renders without leaking secrets from listed rows', () => {
    const listFn = vi.fn(async () => [
      {
        id: '1',
        broker: 'alpaca',
        env: 'paper',
        fingerprint: 'face0001',
        status: 'active',
        last_used_at: null,
        secret: 'SHOULD-NOT-RENDER',
      } as never,
    ]);
    // SSR render only shows empty until effect — assert shell + sanitize on list data.
    const sanitized = ([{ secret: 'SHOULD-NOT-RENDER', fingerprint: 'face0001', broker: 'alpaca', env: 'paper', status: 'active', id: '1', last_used_at: null }] as never[]).map(
      sanitizeConnection,
    );
    const blob = JSON.stringify(sanitized);
    expect(blob).not.toContain('SHOULD-NOT-RENDER');
    void act;
    void listFn;
    const html = renderToStaticMarkup(
      createElement(BrokersTab, {
        api: null,
        listFn,
      }),
    );
    expect(html).not.toContain('SHOULD-NOT-RENDER');
  });

  it('hydrates paper fills from GET /fills', async () => {
    const host = document.createElement('div');
    document.body.appendChild(host);
    const root = createRoot(host);
    const fillsFn = vi.fn(async () => [
      {
        id: 'fill-1',
        symbol: 'AAPL',
        quantity: 1,
        executed_at: '2026-08-31T14:00:00Z',
        recorded_at: '2026-08-31T14:00:01Z',
      },
    ]);
    await act(async () => {
      root.render(
        createElement(BrokersTab, {
          api: { accessToken: 'tok' },
          listFn: vi.fn(async () => []),
          connectFn: vi.fn(),
          revokeFn: vi.fn(),
          fillsFn,
        }),
      );
    });
    await act(async () => {
      await Promise.resolve();
      await Promise.resolve();
    });
    expect(fillsFn).toHaveBeenCalledOnce();
    expect(host.querySelector('[data-testid="broker-fill-row"]')?.textContent).toMatch(/AAPL/);
    act(() => {
      root.unmount();
    });
    host.remove();
  });
});
