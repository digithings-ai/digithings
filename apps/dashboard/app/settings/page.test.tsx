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
vi.mock('@/lib/auth-context', () => ({
  useAuth: () => ({
    session: { access_token: 'tok' },
    user: { email: 'obs@example.com' },
  }),
}));
vi.mock('@/lib/use-entitlement', () => ({
  usePlanTier: () => entitlement.tier,
  useCanAccessProduct: () => false,
  useAccessSnapshot: () => ({ effectivePlanTier: 'free' }),
}));
vi.mock('@/components/settings/account-section', () => ({
  AccountIdentity: () => createElement('div', null, 'identity-body'),
}));
vi.mock('@/components/settings/profile-tab', () => ({
  ProfileTab: () => createElement('div', null, 'profile-body'),
}));
vi.mock('@/components/settings/pipeline-tab', () => ({
  PipelineTab: () => createElement('div', null, 'pipeline-body'),
}));
vi.mock('@/components/settings/connections-section', () => ({
  ConnectionsSection: ({ visibleTabs }: { visibleTabs: string[] }) =>
    createElement('div', null, `connections-body:${visibleTabs.join(',')}`),
}));
vi.mock('@/components/settings/notify-tab', () => ({
  NotifyTab: () => createElement('div', null, 'notify-body'),
}));
vi.mock('@/components/settings/plan-section', () => ({
  PlanSection: () => createElement('div', null, 'plan-body'),
}));
vi.mock('@/components/settings/appearance-section', () => ({
  AppearanceSection: () => createElement('div', null, 'appearance-body'),
}));
vi.mock('@/components/settings/system-section', () => ({
  SystemSection: () => createElement('div', { 'data-testid': 'settings-about' }, 'system-body'),
}));

import SettingsPage from './page';

const q = (c: HTMLElement, id: string) => c.querySelector(`[data-testid="${id}"]`);

describe('Settings page sections', () => {
  let container: HTMLDivElement;
  let root: Root;

  const render = async () => {
    await act(async () => {
      root.render(createElement(SettingsPage));
    });
  };

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

  it('Observer sees Account, Plan, Notifications, Appearance, System only', async () => {
    await render();
    for (const id of ['account', 'plan', 'notifications', 'appearance', 'system']) {
      expect(q(container, `settings-section-${id}`)).not.toBeNull();
      expect(q(container, `settings-panel-${id}`)).not.toBeNull();
    }
    expect(q(container, 'settings-section-pipeline')).toBeNull();
    expect(q(container, 'settings-section-connections')).toBeNull();
    expect(container.textContent).not.toContain('profile-body');
    expect(container.textContent).not.toContain('pipeline-body');
    expect(container.textContent).toContain('notify-body');
  });

  it('Studio sees every section, with profile and pipeline bodies', async () => {
    entitlement.tier = 'studio';
    await render();
    const rail = [...container.querySelectorAll('[data-testid^="settings-section-"]')].map((b) =>
      b.getAttribute('data-testid'),
    );
    expect(rail).toEqual(
      ['account', 'pipeline', 'connections', 'plan', 'notifications', 'appearance', 'system'].map(
        (id) => `settings-section-${id}`,
      ),
    );
    expect(container.textContent).toContain('profile-body');
    expect(container.textContent).toContain('pipeline-body');
    expect(container.textContent).toContain('connections-body');
  });

  it('Desk sees Connections (brokers only), no Pipeline or Profile', async () => {
    entitlement.tier = 'desk';
    await render();
    expect(q(container, 'settings-section-connections')).not.toBeNull();
    expect(q(container, 'settings-section-pipeline')).toBeNull();
    expect(container.textContent).not.toContain('profile-body');
    expect(container.textContent).toContain('connections-body:brokers,');
    expect(container.textContent).not.toContain('connections-body:keys');
    expect(container.textContent).not.toMatch(/connections-body:[^A-Z]*\bkeys\b/);
  });

  it('marks the Account rail item current by default', async () => {
    await render();
    expect(q(container, 'settings-section-account')?.getAttribute('aria-current')).toBe('true');
  });

  it('#billing and #about deep links light Plan and System', async () => {
    window.location.hash = 'billing';
    await render();
    expect(q(container, 'settings-section-plan')?.getAttribute('aria-current')).toBe('true');
    expect(container.querySelector('#billing')).not.toBeNull();
  });

  it('#about lights System', async () => {
    window.location.hash = 'about';
    await render();
    expect(q(container, 'settings-section-system')?.getAttribute('aria-current')).toBe('true');
    expect(container.querySelector('#about')).not.toBeNull();
  });

  it('a gated hash on Observer keeps the default section', async () => {
    window.location.hash = 'profile';
    await render();
    expect(q(container, 'settings-section-account')?.getAttribute('aria-current')).toBe('true');
    expect(container.textContent).not.toContain('profile-body');
  });

  it('Stripe return shows a checkout notice and lands on Plan', async () => {
    window.history.replaceState(null, '', '/settings/?tab=billing&checkout=success');
    await render();
    expect(q(container, 'settings-section-plan')?.getAttribute('aria-current')).toBe('true');
    expect(q(container, 'settings-checkout-notice')?.textContent).toContain('Checkout complete');
  });

  it('?checkout=cancel shows the cancelled notice', async () => {
    window.history.replaceState(null, '', '/settings/?checkout=cancel');
    await render();
    expect(q(container, 'settings-checkout-notice')?.textContent).toContain('cancelled');
  });

  it('query tab wins over a conflicting hash', async () => {
    window.history.replaceState(null, '', '/settings/?tab=billing#about');
    await render();
    expect(q(container, 'settings-section-plan')?.getAttribute('aria-current')).toBe('true');
  });

  it('clicking a rail item writes its hash and marks it current', async () => {
    await render();
    await act(async () => {
      (q(container, 'settings-section-plan') as HTMLButtonElement).click();
    });
    expect(window.location.hash).toBe('#plan');
    expect(q(container, 'settings-section-plan')?.getAttribute('aria-current')).toBe('true');
  });

  it('search lists matching settings; choosing one jumps to its section', async () => {
    await render();
    const input = container.querySelector('input') as HTMLInputElement;
    await act(async () => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      set.call(input, 'digest');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    const hits = container.querySelectorAll('[data-testid="settings-search-hit"]');
    expect(hits.length).toBeGreaterThan(0);
    await act(async () => {
      (hits[0] as HTMLButtonElement).click();
    });
    expect(q(container, 'settings-section-notifications')?.getAttribute('aria-current')).toBe('true');
    expect(q(container, 'settings-search-results')).toBeNull();
  });

  it('search with no match says so', async () => {
    await render();
    const input = container.querySelector('input') as HTMLInputElement;
    await act(async () => {
      const set = Object.getOwnPropertyDescriptor(HTMLInputElement.prototype, 'value')!.set!;
      set.call(input, 'zzzzqq');
      input.dispatchEvent(new Event('input', { bubbles: true }));
    });
    expect(q(container, 'settings-search-results')?.textContent).toContain('No matching settings');
  });
});
