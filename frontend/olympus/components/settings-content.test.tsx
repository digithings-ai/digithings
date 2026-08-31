import { createElement } from 'react';
import { renderToStaticMarkup } from 'react-dom/server';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { SettingsContent } from './settings-content';

const mocks = vi.hoisted(() => ({
  pathname: '/settings/',
  theme: 'dark' as 'auto' | 'dark' | 'light',
  setTheme: vi.fn(),
}));

vi.mock('next/navigation', () => ({
  usePathname: () => mocks.pathname,
}));

vi.mock('@/components/theme-provider', () => ({
  useDashboardTheme: () => ({
    theme: mocks.theme,
    setTheme: mocks.setTheme,
  }),
  useAtlasTheme: () => ({
    theme: mocks.theme,
    setTheme: mocks.setTheme,
  }),
}));

function render(overrides: Partial<Parameters<typeof SettingsContent>[0]> = {}): string {
  return renderToStaticMarkup(
    createElement(SettingsContent, {
      lastRunDate: '2026-06-23',
      lastRunAt: '2026-06-23T16:13:04Z',
      runType: 'baseline',
      version: 'v0.4.0',
      dataSourceHost: 'abcdefgh.supabase.co',
      ...overrides,
    })
  );
}

describe('SettingsContent', () => {
  beforeEach(() => {
    mocks.pathname = '/settings/';
    mocks.theme = 'dark';
    mocks.setTheme.mockClear();
  });

  it('hides the redundant All settings link on the trailing-slash settings route', () => {
    expect(render()).not.toContain('All settings');
  });

  it('marks the active theme button with aria-pressed', () => {
    const html = render();
    expect(html).toMatch(/aria-pressed="true"[^>]*>Dark/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>Auto/);
    expect(html).toMatch(/aria-pressed="false"[^>]*>Light/);
  });

  it('shows the build version and friendly data-source host in About', () => {
    const html = render();
    expect(html).toContain('v0.4.0');
    expect(html).toContain('abcdefgh.supabase.co');
  });

  it('renders the empty-state line when no run is recorded', () => {
    const html = render({ lastRunDate: null, lastRunAt: null, runType: null });
    expect(html).toContain('No pipeline runs yet');
  });

  it('links Docs to /pipeline, never /architecture or /system', () => {
    const html = render();
    expect(html).toContain('href="/pipeline"');
    expect(html).toContain('Pipeline');
    expect(html).not.toContain('/architecture');
    expect(html).not.toContain('href="/system"');
  });

  it('uses no off-palette fin-blue literals', () => {
    expect(render()).not.toContain('fin-blue');
  });

  it('page variant shows Custom-tier workspace gates and Billing anchor', () => {
    const locked = render({ variant: 'page', tier: 'free' });
    expect(locked).toContain('settings-workspace-gates');
    expect(locked).toContain('locked-surface');
    expect(locked).toContain('settings-billing-anchor');
    expect(locked).toContain('id="billing"');

    const unlocked = render({ variant: 'page', tier: 'custom' });
    expect(unlocked).toContain('tier-unlocked-note');
    expect(unlocked).not.toContain('locked-surface');
  });

  it('popover variant omits workspace gates (keep chrome compact)', () => {
    const html = render({ variant: 'popover', tier: 'free' });
    expect(html).not.toContain('settings-workspace-gates');
  });
});
