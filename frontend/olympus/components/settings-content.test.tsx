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
  useAtlasTheme: () => ({
    theme: mocks.theme,
    setTheme: mocks.setTheme,
  }),
}));

function render(): string {
  return renderToStaticMarkup(createElement(SettingsContent));
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

  it('points Docs at /system, never the retired /architecture', () => {
    const html = render();
    expect(html).toContain('href="/system"');
    expect(html).not.toContain('/architecture');
  });
});
