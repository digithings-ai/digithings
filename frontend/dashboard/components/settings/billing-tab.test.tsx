/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { renderToStaticMarkup } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';
import { BillingTab } from './billing-tab';

describe('BillingTab (static)', () => {
  it('renders billing not configured when envs absent', () => {
    const html = renderToStaticMarkup(
      createElement(BillingTab, { api: null, configured: false }),
    );
    expect(html).toContain('billing-not-configured');
    expect(html).toContain('Billing is not configured');
  });

  it('defaults to annual as a discount over monthly list prices', () => {
    const html = renderToStaticMarkup(
      createElement(BillingTab, {
        api: { accessToken: 'tok' },
        configured: true,
        checkoutFn: vi.fn(),
        portalFn: vi.fn(),
      }),
    );
    expect(html).toContain('data-interval="annual"');
    expect(html).toContain('Annual · 20% off');
    expect(html).toContain('billing-plan-table');
    expect(html).toContain('grid-cols-[minmax(0,1fr)_9.5rem_10.5rem]');
    expect(html).toContain('billing-checkout-studio');
    expect(html).toContain('billing-checkout-desk');
    expect(html).toContain('billing-checkout-brief');
    expect(html).toContain('billing-portal');
    expect(html).not.toContain('billing-checkout-custom');
    expect(html).not.toContain('billing-checkout-baseline');
    expect(html).toContain('$8/mo');
    expect(html).toContain('$24/mo');
    expect(html).toContain('$80/mo');
    expect(html).toContain('billed $96/yr');
    expect(html).toContain('billed $288/yr');
    expect(html).toContain('billed $960/yr');
    expect(html).not.toContain('2 months free');
    expect(html).toContain('data-testid="billing-price-discount">20% off');
    expect(html).toContain('<s data-testid="billing-price-list">$10/mo</s>');
    expect(html).toContain('<s data-testid="billing-price-list">$30/mo</s>');
    expect(html).toContain('<s data-testid="billing-price-list">$100/mo</s>');
  });
});

describe('BillingTab (interval)', () => {
  let root: Root | null = null;
  let host: HTMLElement | null = null;

  afterEach(() => {
    act(() => {
      root?.unmount();
    });
    host?.remove();
    root = null;
    host = null;
  });

  async function mount(ui: React.ReactElement): Promise<HTMLElement> {
    host = document.createElement('div');
    document.body.appendChild(host);
    root = createRoot(host);
    await act(async () => {
      root!.render(ui);
    });
    return host;
  }

  it('switches to monthly list prices and checks out on the selected interval', async () => {
    const checkoutFn = vi.fn(async () => ({ url: null }));
    const el = await mount(
      createElement(BillingTab, {
        api: { accessToken: 'tok' },
        configured: true,
        checkoutFn,
        portalFn: vi.fn(),
      }),
    );
    expect(
      el.querySelector('[data-testid="settings-billing-tab"]')?.getAttribute('data-interval'),
    ).toBe('annual');

    await act(async () => {
      (el.querySelector('[data-testid="billing-interval-monthly"]') as HTMLButtonElement).click();
    });
    const tab = el.querySelector('[data-testid="settings-billing-tab"]');
    expect(tab?.getAttribute('data-interval')).toBe('monthly');
    expect(tab?.textContent).toContain('$10/mo');
    expect(tab?.textContent).toContain('$30/mo');
    expect(tab?.textContent).toContain('$100/mo');
    expect(tab?.querySelector('[data-testid="billing-price-list"]')).toBeNull();
    expect(tab?.querySelector('[data-testid="billing-price-caption"]')).toBeNull();
    expect(tab?.textContent).not.toContain('billed $100/yr');

    await act(async () => {
      (el.querySelector('[data-testid="billing-checkout-desk"]') as HTMLButtonElement).click();
    });
    expect(checkoutFn).toHaveBeenCalledWith(
      { accessToken: 'tok' },
      { tier: 'desk', interval: 'monthly' },
    );

    await act(async () => {
      (el.querySelector('[data-testid="billing-interval-annual"]') as HTMLButtonElement).click();
    });
    await act(async () => {
      (el.querySelector('[data-testid="billing-checkout-studio"]') as HTMLButtonElement).click();
    });
    expect(checkoutFn).toHaveBeenLastCalledWith(
      { accessToken: 'tok' },
      { tier: 'studio', interval: 'annual' },
    );
  });
});
