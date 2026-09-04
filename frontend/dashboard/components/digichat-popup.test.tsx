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
  mode: 'bar',
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

  it('renders ask digichat rectangle launcher for Desk+', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const btn = container.querySelector('#digichat-popup-launcher');
    expect(btn).not.toBeNull();
    expect(btn?.textContent).toBe('ask digichat');
    expect(btn?.getAttribute('data-mode')).toBe('bar');
    expect(btn?.getAttribute('aria-expanded')).toBe('false');
  });

  it('opens panel, toggles close label, and sets iframe src on click', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const btn = container.querySelector(
      '#digichat-popup-launcher',
    ) as HTMLButtonElement;
    act(() => {
      btn.click();
    });
    expect(btn.getAttribute('aria-expanded')).toBe('true');
    expect(btn.textContent).toBe('close');
    const iframe = container.querySelector(
      '#digichat-popup-iframe',
    ) as HTMLIFrameElement;
    expect(iframe).not.toBeNull();
    expect(iframe.src).toContain('https://digithings.ai/embed');
    expect(iframe.src).toContain('host=digiquant.io');
    expect(iframe.src).toContain('layout=embed');
    const panel = container.querySelector('#digichat-popup-panel');
    expect(panel?.getAttribute('data-expanded')).toBe('0');
  });

  it('expands and collapses via the panel control', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const launcher = container.querySelector(
      '#digichat-popup-launcher',
    ) as HTMLButtonElement;
    act(() => {
      launcher.click();
    });
    const expand = container.querySelector(
      '#digichat-popup-expand',
    ) as HTMLButtonElement;
    expect(expand).not.toBeNull();
    act(() => {
      expand.click();
    });
    expect(
      container.querySelector('#digichat-popup-panel')?.getAttribute('data-expanded'),
    ).toBe('1');
    expect(expand.getAttribute('aria-pressed')).toBe('true');
    act(() => {
      expand.click();
    });
    expect(
      container.querySelector('#digichat-popup-panel')?.getAttribute('data-expanded'),
    ).toBe('0');
  });

  it('launcher click dismisses an open panel', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const btn = container.querySelector(
      '#digichat-popup-launcher',
    ) as HTMLButtonElement;
    act(() => {
      btn.click();
    });
    expect(btn.getAttribute('aria-expanded')).toBe('true');
    act(() => {
      btn.click();
    });
    expect(btn.getAttribute('aria-expanded')).toBe('false');
    expect(btn.textContent).toBe('ask digichat');
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
