/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const canAccess = vi.hoisted(() => ({ value: false }));
const redeem = vi.hoisted(() => ({
  fn: vi.fn(async () => ({ ok: true, already_granted: false, product_key: 'fx_hub' })),
}));
const refresh = vi.hoisted(() => ({ fn: vi.fn() }));
const authEnabled = vi.hoisted(() => ({ value: true }));

vi.mock('next/link', () => ({
  default: (props: { children?: unknown; href?: string }) =>
    createElement('a', { href: props.href }, props.children as never),
}));

vi.mock('@/lib/supabase', () => ({
  isOlympusAuthEnabled: () => authEnabled.value,
}));

vi.mock('@/lib/use-entitlement', () => ({
  useCanAccessProduct: () => canAccess.value,
  requestAccessRefresh: () => refresh.fn(),
}));

vi.mock('@/lib/auth-context', async () => {
  const react = await vi.importActual<typeof import('react')>('react');
  return { AuthContext: react.createContext(null) };
});

vi.mock('@/lib/settings-api', () => ({
  redeemInvite: (...args: unknown[]) => redeem.fn(...args),
  SettingsHttpError: class SettingsHttpError extends Error {
    code = 'INVITE_INVALID';
    status = 403;
  },
}));

import { AuthContext } from '@/lib/auth-context';
import { ClientProductGate } from './client-product-gate';

describe('ClientProductGate', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    canAccess.value = false;
    authEnabled.value = true;
    redeem.fn.mockClear();
    refresh.fn.mockClear();
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  function renderGate(child = 'hub-body') {
    return createElement(
      AuthContext.Provider,
      { value: { session: { access_token: 'sess-tok' } } as never },
      createElement(ClientProductGate, { productKey: 'fx_hub', title: 'FX Hub' }, child),
    );
  }

  it('shows the invite form when auth is on and the product is locked', async () => {
    await act(async () => {
      root.render(renderGate());
    });
    expect(container.textContent).toContain('Team invite code');
    expect(container.textContent).not.toContain('hub-body');
    expect(container.querySelector('[data-testid="client-product-invite-form"]')).not.toBeNull();
  });

  it('redeems a valid invite and then renders children', async () => {
    await act(async () => {
      root.render(renderGate());
    });
    const input = container.querySelector(
      '[data-testid="client-product-invite-input"]',
    ) as HTMLInputElement;
    await act(async () => {
      const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')
        ?.set;
      proto?.call(input, '12x-desk-invite-alpha');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const form = container.querySelector('[data-testid="client-product-invite-form"]');
    await act(async () => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(redeem.fn).toHaveBeenCalledWith(
      { accessToken: 'sess-tok' },
      { code: '12x-desk-invite-alpha', product_key: 'fx_hub' },
    );
    expect(refresh.fn).toHaveBeenCalledOnce();
    expect(container.textContent).toContain('hub-body');
  });

  it('refuses a short code without calling the backend', async () => {
    await act(async () => {
      root.render(renderGate());
    });
    const input = container.querySelector(
      '[data-testid="client-product-invite-input"]',
    ) as HTMLInputElement;
    await act(async () => {
      const proto = Object.getOwnPropertyDescriptor(window.HTMLInputElement.prototype, 'value')
        ?.set;
      proto?.call(input, 'short');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const form = container.querySelector('[data-testid="client-product-invite-form"]');
    await act(async () => {
      form!.dispatchEvent(new Event('submit', { bubbles: true, cancelable: true }));
    });
    expect(redeem.fn).not.toHaveBeenCalled();
    expect(container.textContent).toMatch(/not valid/i);
  });
});
