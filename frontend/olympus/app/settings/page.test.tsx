/**
 * @vitest-environment happy-dom
 */
import { createElement, act } from 'react';
import { createRoot, type Root } from 'react-dom/client';
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

  it('Custom sees the full tab set including Profile', async () => {
    entitlement.tier = 'custom';
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
    expect(container.querySelector('[data-testid="settings-tab-profile"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-brokers"]')).not.toBeNull();
    expect(container.querySelector('[data-testid="settings-tab-keys"]')).not.toBeNull();
    expect(container.textContent).toContain('profile-body');
  });
});
