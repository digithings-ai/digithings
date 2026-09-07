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
import {
  DIGICHAT_PAGE_CONTEXT,
  DIGICHAT_READY,
  DIGICHAT_THEME,
  DIGICHAT_UPGRADE_BODY,
  DIGICHAT_UPGRADE_CTA_HREF,
  DIGICHAT_UPGRADE_CTA_LABEL,
  DIGICHAT_UPGRADE_TITLE,
  type DigichatPopupConfig,
} from '@/lib/digichat-popup';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

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
    vi.useFakeTimers();
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    vi.useRealTimers();
  });

  it('renders launcher with an upgrade CTA (disabled chat) for Brief (#3662)', () => {
    act(() => {
      root.render(
        createElement(DigichatPopup, { tier: 'brief', config: CFG }),
      );
    });
    // Launcher is visible, but opening it shows the upgrade block — never chat.
    expect(container.querySelector('[data-digichat-popup]')).not.toBeNull();
    const btn = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    expect(btn).not.toBeNull();
    act(() => {
      btn.click();
    });
    expect(document.body.querySelector('.digichat-launcher__panel')).not.toBeNull();
    const cta = document.body.querySelector('[data-testid="digichat-upgrade-cta"]');
    expect(cta).not.toBeNull();
    expect(cta?.textContent).toContain(DIGICHAT_UPGRADE_TITLE);
    expect(cta?.textContent).toContain(DIGICHAT_UPGRADE_BODY);
    const link = cta?.querySelector('a');
    expect(link?.textContent).toBe(DIGICHAT_UPGRADE_CTA_LABEL);
    expect(link?.getAttribute('href')).toBe(DIGICHAT_UPGRADE_CTA_HREF);
  });

  it('builds no iframe for baseline, so free/brief never burn turns (#3662)', () => {
    act(() => {
      root.render(
        createElement(DigichatPopup, { tier: 'free', config: CFG }),
      );
    });
    const btn = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    act(() => {
      btn.click();
    });
    expect(document.body.querySelector('#digichat-popup-iframe')).toBeNull();
  });

  it('renders launcher for Desk+ when config is present', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const btn = document.body.querySelector('.digichat-launcher__trigger');
    expect(btn).not.toBeNull();
    expect(btn?.getAttribute('aria-expanded')).toBe('false');
  });

  it('shows no upgrade CTA for Desk+ (entitled chat, #3662)', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const btn = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    act(() => {
      btn.click();
    });
    expect(
      document.body.querySelector('[data-testid="digichat-upgrade-cta"]'),
    ).toBeNull();
    expect(document.body.querySelector('#digichat-popup-iframe')).not.toBeNull();
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

  it('keeps the iframe mounted across close and reopen', () => {
    act(() => {
      root.render(createElement(DigichatPopup, { tier: 'desk', config: CFG }));
    });
    const trigger = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    act(() => trigger.click());
    const iframe = document.body.querySelector(
      '#digichat-popup-iframe',
    ) as HTMLIFrameElement;
    const postMessage = vi.spyOn(iframe.contentWindow!, 'postMessage');
    act(() => {
      window.dispatchEvent(
        new MessageEvent('message', {
          origin: CFG.origin,
          data: { type: DIGICHAT_READY },
        }),
      );
    });
    const readyCallCount = postMessage.mock.calls.length;

    const close = document.body.querySelector(
      '.digichat-launcher__close',
    ) as HTMLButtonElement;
    act(() => close.click());
    act(() => vi.advanceTimersByTime(340));
    expect(document.body.querySelector('#digichat-popup-iframe')).toBe(iframe);

    const reopenedTrigger = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    act(() => reopenedTrigger.click());
    expect(document.body.querySelector('#digichat-popup-iframe')).toBe(iframe);
    const reopenTypes = postMessage.mock.calls
      .slice(readyCallCount)
      .map(([message]) => (message as { type?: string }).type);
    expect(reopenTypes).toEqual(
      expect.arrayContaining([DIGICHAT_THEME, DIGICHAT_PAGE_CONTEXT]),
    );
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
