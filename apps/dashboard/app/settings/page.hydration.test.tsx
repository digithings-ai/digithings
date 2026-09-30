/**
 * @vitest-environment happy-dom
 *
 * The settings rail must survive hydration on a deep link.
 *
 * Kept apart from page.test.tsx because every section body renders the SAME
 * markup here. That is the only shape where the bug is observable: when bodies
 * differ, hydration hits a structural mismatch and React re-renders the whole
 * root, so the highlight comes out right for the wrong reason. When they match,
 * the only difference left is an attribute, which React does not repair, so a
 * `useState` initializer reading the URL leaves the rail highlighting whatever
 * the prerender highlighted.
 */
import { act, createElement } from 'react';
import { hydrateRoot, type Root } from 'react-dom/client';
import { renderToString } from 'react-dom/server';
import { afterEach, describe, expect, it, vi } from 'vitest';

const Body = vi.hoisted(() => {
  const B = () => createElement('div', { 'data-body': '1' }, 'section-body');
  B.displayName = 'SectionBody';
  return B;
});

vi.mock('next/navigation', () => ({ usePathname: () => '/settings' }));
vi.mock('@/lib/dashboard-context', () => ({
  useDashboard: () => ({ data: { portfolio: { meta: null } } }),
}));
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({ session: { access_token: 'tok' }, user: { email: 'obs@example.com' } }),
}));
vi.mock('@/lib/use-entitlement', () => ({
  usePlanTier: () => 'free',
  useCanAccessProduct: () => false,
  useAccessSnapshot: () => ({ effectivePlanTier: 'free' }),
}));
vi.mock('@/components/settings/account-section', () => ({ AccountIdentity: Body }));
vi.mock('@/components/settings/profile-tab', () => ({ ProfileTab: Body }));
vi.mock('@/components/settings/pipeline-tab', () => ({ PipelineTab: Body }));
vi.mock('@/components/settings/connections-section', () => ({ ConnectionsSection: Body }));
vi.mock('@/components/settings/notify-tab', () => ({ NotifyTab: Body }));
vi.mock('@/components/settings/plan-section', () => ({ PlanSection: Body }));
vi.mock('@/components/settings/appearance-section', () => ({ AppearanceSection: Body }));
vi.mock('@/components/settings/system-section', () => ({ SystemSection: Body }));

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

  const current = (container: HTMLElement) =>
    [...container.querySelectorAll('[aria-current="true"]')].map((el) => el.textContent?.trim() ?? '');

  it('lights the linked section, and only that one', async () => {
    expect(current(await hydrateAt('?tab=billing'))).toEqual(['Plan & billing']);
  });

  it('stays on the default section with no tab param', async () => {
    expect(current(await hydrateAt(''))).toEqual(['Account']);
  });
});
