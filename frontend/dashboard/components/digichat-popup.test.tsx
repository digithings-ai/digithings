/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

vi.mock('@/lib/use-entitlement', () => ({
  usePlanTier: () => 'desk',
}));

import DigichatPopup from './digichat-popup';
import type { DigichatPopupConfig } from '@/lib/digichat-popup';

const CFG: DigichatPopupConfig = {
  origin: 'https://digithings.ai',
  host: 'digiquant.io',
  mode: 'dot',
  pageContext: true,
  accent: '#3dd6c4',
  welcome: 'hello',
  suggestions: ['a'],
  placeholder: 'ask…',
};

describe('DigichatPopup', () => {
  let container: HTMLDivElement;
  let root: Root;

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    document.documentElement.setAttribute('data-theme', 'dark');
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
  });

  it('renders nothing for Brief (below Desk)', () => {
    act(() => {
      root.render(
        createElement(DigichatPopup, { tier: 'brief', config: CFG }),
      );
    });
    expect(container.querySelector('[data-digichat-popup]')).toBeNull();
  });

  it('renders launcher for Desk+ when config is present', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const btn = document.body.querySelector('.digichat-launcher__trigger');
    expect(btn).not.toBeNull();
    expect(btn?.getAttribute('aria-expanded')).toBe('false');
  });

  it('opens the shared panel and sets iframe src on click', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const btn = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    act(() => {
      btn.click();
    });
    expect(document.body.querySelector('.digichat-launcher__panel')).not.toBeNull();
    const iframe = document.body.querySelector(
      '#digichat-popup-iframe',
    ) as HTMLIFrameElement;
    expect(iframe).not.toBeNull();
    expect(iframe.src).toContain('https://digithings.ai/embed');
    expect(iframe.src).toContain('host=digiquant.io');
    expect(iframe.src).toContain('layout=embed');
  });

  it('renders nothing when config is null', () => {
    act(() => {
      root.render(
        createElement(DigichatPopup, { tier: 'desk', config: null }),
      );
    });
    expect(container.querySelector('[data-digichat-popup]')).toBeNull();
  });
});
