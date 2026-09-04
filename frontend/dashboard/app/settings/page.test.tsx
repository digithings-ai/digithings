/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const entitlement = vi.hoisted(() => ({ tier: 'free' as string }));

vi.mock('next/navigation', () => ({ usePathname: () => '/settings' }));
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ data: { portfolio: { meta: null } } }),
}));
vi.mock('@/components/app-shell-context', () => ({
  useAppShell: () => ({ openCommandPalette: () => {} }),
}));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    session: { access_token: 'tok' },
    user: { email: 'obs@example.com' },
  }),
}));
vi.mock('@/lib/use-entitlement', () => ({
  usePlanTier: () => entitlement.tier,
}));
vi.mock('@/components/settings/profile-tab', () => ({
  ProfileTab: () => createElement('div', { 'data-profile': '1' }, 'profile-body'),
}));
vi.mock('@/components/settings/pipeline-tab', () => ({
  PipelineTab: () => createElement('div', { 'data-pipeline': '1' }, 'pipeline-body'),
}));
vi.mock('@/components/settings/keys-tab', () => ({
  KeysTab: () => createElement('div', { 'data-keys': '1' }, 'keys-body'),
}));
vi.mock('@/components/settings/brokers-tab', () => ({
  BrokersTab: () => createElement('div', { 'data-brokers': '1' }, 'brokers-body'),
}));
vi.mock('@/components/settings/notify-tab', () => ({
  NotifyTab: () => createElement('div', { 'data-notify': '1' }, 'notify-body'),
}));
vi.mock('@/components/settings/billing-tab', () => ({
  BillingTab: () => createElement('div', { 'data-billing': '1' }, 'billing-body'),
}));
vi.mock('@/components/settings-content', () => ({
  SettingsContent: () => createElement('div', { 'data-about': '1' }, 'about-body'),
}));
vi.mock('@/components/settings/remaining-hop-status', () => ({
  RemainingHopStatus: () =>
    createElement('div', { 'data-testid': 'remaining-hop-status' }, 'remaining-hops'),
}));
vi.mock('@/components/subpage-tab-bar', () => ({
  subpageTabButtonClass: (active: boolean) => (active ? 'tab-on' : 'tab-off'),
  SubpageStickyTabBar: ({ children }: { children?: unknown }) =>
    createElement('div', { 'data-tabs': '1' }, children as never),
}));

import SettingsPage from './page';

describe('Settings page tab visibility', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    entitlement.tier = 'free';
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    window.location.hash = '';
    window.history.replaceState(null, '', '/settings');
  });

  it('Observer sees Notifications / Billing / About only — no Profile or Brokers', async () => {
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.querySelector('[data-testid="settings-tab-notifications"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-billing"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-about"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-profile"]')).toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-pipeline"]')).toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-keys"]')).toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-brokers"]')).toBeNull();
    expect(container.textContent).toContain('notify-body');
    expect(container.textContent).not.toContain('profile-body');
  });

  it('Studio sees the full tab set including Profile', async () => {
    entitlement.tier = 'studio';
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.querySelector('[data-testid="settings-tab-profile"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-brokers"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-keys"]')).not.toBeNull();
    expect(container.textContent).toContain('profile-body');
  });

  it('Desk sees Brokers but not Profile / Pipeline / Keys', async () => {
    entitlement.tier = 'desk';
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.querySelector('[data-testid="settings-tab-brokers"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-profile"]')).toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-pipeline"]')).toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-keys"]')).toBeNull();
  });

  it('opens Billing when the URL hash is #billing', async () => {
    window.location.hash = 'billing';
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.textContent).toContain('billing-body');
    expect(container.textContent).not.toContain('notify-body');
    expect(container.querySelector('#billing')).not.toBeNull();
  });

  it('ignores a gated hash on Observer instead of showing Profile', async () => {
    window.location.hash = 'profile';
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.textContent).toContain('notify-body');
    expect(container.textContent).not.toContain('profile-body');
  });

  it('opens Billing from Stripe return ?tab=billing&checkout=success', async () => {
    window.history.replaceState(null, '', '/settings/?tab=billing&checkout=success');
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.textContent).toContain('billing-body');
    expect(container.textContent).not.toContain('notify-body');
  });

  it('opens Billing from ?checkout=cancel when tab is omitted', async () => {
    window.history.replaceState(null, '', '/settings/?checkout=cancel');
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.textContent).toContain('billing-body');
  });

  it('query tab wins over a conflicting hash', async () => {
    window.history.replaceState(null, '', '/settings/?tab=billing#about');
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.textContent).toContain('billing-body');
    expect(container.textContent).not.toContain('about-body');
  });

  it('Observer About mounts remaining hops next to the about body', async () => {
    window.location.hash = 'about';
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.querySelector('[data-testid="settings-about"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="remaining-hop-status"]')).not.toBeNull();
    expect(container.textContent).toContain('remaining-hops');
    expect(container.textContent).toContain('about-body');
    expect(container.textContent).not.toContain('notify-body');
  });

  it('hydrating a deep link lights the linked tab, not the default one', async () => {
    // Prerendered markup knows no URL (static export), so the highlight has to
    // survive hydration as a real update — React does not repair a mismatched
    // attribute. See TwelveXClient.hydration.test.tsx for the same seam.
    window.history.replaceState(null, '', '/settings/');
    const prerendered = document.createElement('div');
    prerendered.innerHTML = renderToString(createElement(SettingsPage));
    document.body.appendChild(prerendered);

    window.history.replaceState(null, '', '/settings/?tab=billing');
    let hydrated!: Root;
    await act(async () => {
      hydrated = hydrateRoot(prerendered, createElement(SettingsPage));
    });

    const on = [...prerendered.querySelectorAll('.tab-on')].map((el) => el.textContent?.trim());
    expect(on).toEqual(['Billing']);

    act(() => {
      hydrated.unmount();
    });
    prerendered.remove();
  });

  it('clicking Billing writes #billing and shows the billing body', async () => {
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    const billing = container.querySelector('[data-testid="settings-tab-billing"]');
    expect(billing).not.toBeNull();
    await act(async () => {
      (billing as HTMLButtonElement).click();
    });
    expect(window.location.hash).toBe('#billing');
    expect(container.textContent).toContain('billing-body');
    expect(container.textContent).not.toContain('notify-body');
  });
});
