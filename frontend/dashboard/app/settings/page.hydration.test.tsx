/**
 * @vitest-environment happy-dom
 *
 * The settings tab strip must survive hydration on a deep link.
 *
 * Kept apart from page.test.tsx because it needs every tab body to render the
 * SAME markup. That is not an arbitrary simplification — it is the only shape
 * where the bug is observable. When the bodies differ, hydration hits a
 * structural mismatch, React throws the server HTML away and re-renders the
 * whole root, and the tab classes come out right for the wrong reason. When
 * they match (the real hazard: two tabs sharing one loading state, which is how
 * the FX workspace shipped this bug), the only difference left is an attribute
 * — and React does not repair those, so a `useState` initializer reading the
 * URL leaves the strip highlighting whatever the prerender highlighted.
 */
import { act, createElement } from 'react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

/* One component behind every tab — see the file docblock. */
const TabBody = vi.hoisted(() => {
  const Body = () => createElement('div', { 'data-body': '1' }, 'tab-body');
  Body.displayName = 'TabBody';
  return Body;
});

vi.mock('next/navigation', () => ({ usePathname: () => '/settings' }));
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ data: { portfolio: { meta: null } } }),
}));
vi.mock('@/components/app-shell-context', () => ({
  useAppShell: () => ({ openCommandPalette: () => {} }),
}));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ session: { access_token: 'tok' }, user: { email: 'obs@example.com' } }),
}));
vi.mock('@/lib/use-entitlement', () => ({ usePlanTier: () => 'free' }));

vi.mock('@/components/settings/profile-tab', () => ({ ProfileTab: TabBody }));
vi.mock('@/components/settings/pipeline-tab', () => ({ PipelineTab: TabBody }));
vi.mock('@/components/settings/keys-tab', () => ({ KeysTab: TabBody }));
vi.mock('@/components/settings/brokers-tab', () => ({ BrokersTab: TabBody }));
vi.mock('@/components/settings/notify-tab', () => ({ NotifyTab: TabBody }));
vi.mock('@/components/settings/billing-tab', () => ({ BillingTab: TabBody }));
vi.mock('@/components/settings-content', () => ({ SettingsContent: TabBody }));
vi.mock('@/components/settings/remaining-hop-status', () => ({ RemainingHopStatus: TabBody }));
vi.mock('@/components/subpage-tab-bar', () => ({
  subpageTabButtonClass: (active: boolean) => (active ? 'tab-on' : 'tab-off'),
  SubpageStickyTabBar: ({ children }: { children?: unknown }) =>
    createElement('div', { 'data-tabs': '1' }, children as never),
}));

import SettingsPage from './page';

describe('Settings deep-link hydration', () => {
  let open: { container: HTMLDivElement; root: Root } | null = null;

  afterEach(() => {
    if (open) {
      const { container, root } = open;
      act(() => {
        root.unmount();
      });
      container.remove();
      open = null;
    }
    window.history.replaceState(null, '', '/settings/');
  });

  /** Prerender with no query string (the static export), then hydrate under one. */
  async function hydrateAt(search: string) {
    window.history.replaceState(null, '', '/settings/');
    const container = document.createElement('div');
    container.innerHTML = renderToString(createElement(SettingsPage));
    document.body.appendChild(container);

    window.history.replaceState(null, '', `/settings/${search}`);
    let root!: Root;
    await act(async () => {
      root = hydrateRoot(container, createElement(SettingsPage));
    });
    open = { container, root };
    return container;
  }

  const activeTabs = (container: HTMLElement) =>
    [...container.querySelectorAll('.tab-on')].map((el) => el.textContent?.trim() ?? '');

  it('lights the linked tab, and only that tab', async () => {
    expect(activeTabs(await hydrateAt('?tab=billing'))).toEqual(['Billing']);
  });

  it('stays on the default tab with no tab param', async () => {
    expect(activeTabs(await hydrateAt(''))).toEqual(['Notifications']);
  });
});
