/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

const entitlementMock = vi.hoisted(() => ({
  planTier: 'desk' as const,
  canFxHub: false,
}));

vi.mock('@/lib/use-entitlement', () => ({
  usePlanTier: () => entitlementMock.planTier,
  useCanAccessProduct: () => entitlementMock.canFxHub,
}));

vi.mock('next/navigation', () => ({
  usePathname: () => '/',
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
  PAGE_CONTEXT_RESEND_DEBOUNCE_MS,
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
    entitlementMock.canFxHub = false;
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
    // The upgrade-only panel must never offer New chat (#3785).
    expect(document.body.querySelector('.digichat-launcher__new')).toBeNull();
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

  it('renders nothing for an fx_hub-only grantee on the free tier (12x invite)', () => {
    entitlementMock.canFxHub = true;
    act(() => {
      root.render(
        createElement(DigichatPopup, { tier: 'free', config: CFG }),
      );
    });
    // No launcher, no upgrade CTA, no iframe — FX Hub-only viewers are not on
    // the DigiQuant pipeline subscription (#3662 reversed for the 12x invite).
    expect(document.body.querySelector('.digichat-launcher__trigger')).toBeNull();
    expect(
      document.body.querySelector('[data-testid="digichat-upgrade-cta"]'),
    ).toBeNull();
    expect(document.body.querySelector('#digichat-popup-iframe')).toBeNull();
  });

  it('renders upgrade CTA, no iframe, for a Brief subscriber with an fx_hub grant (#4305)', () => {
    entitlementMock.canFxHub = true;
    act(() => {
      root.render(
        createElement(DigichatPopup, { tier: 'brief', config: CFG }),
      );
    });
    // fx_hub gating is free-only: a paying Brief subscriber keeps the popup
    // and its upgrade CTA — never the fx_hub-only hidden state.
    const btn = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    expect(btn).not.toBeNull();
    act(() => {
      btn.click();
    });
    const cta = document.body.querySelector(
      '[data-testid="digichat-upgrade-cta"]',
    );
    expect(cta).not.toBeNull();
    expect(cta?.textContent).toContain(DIGICHAT_UPGRADE_TITLE);
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

  it('sends page-context once per open even if ready fires twice', () => {
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
    const ready = () =>
      window.dispatchEvent(
        new MessageEvent('message', {
          origin: CFG.origin,
          data: { type: DIGICHAT_READY },
        }),
      );
    act(() => ready());
    act(() => ready());
    const pageContextCalls = postMessage.mock.calls.filter(
      ([message]) => (message as { type?: string }).type === DIGICHAT_PAGE_CONTEXT,
    );
    expect(pageContextCalls).toHaveLength(1);
  });

  it('resends page context when the observed page content changes', async () => {
    const main = document.createElement('main');
    main.innerHTML = '<h1>House book</h1>';
    document.body.appendChild(main);
    try {
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
      const contextCalls = () =>
        postMessage.mock.calls.filter(
          ([message]) =>
            (message as { type?: string }).type === DIGICHAT_PAGE_CONTEXT,
        );
      expect(contextCalls()).toHaveLength(1);
      expect((contextCalls()[0][0] as { text: string }).text).toContain(
        'House book',
      );

      act(() => {
        main.innerHTML = '<h1>Portfolio</h1>';
      });
      await act(async () => {});
      act(() => {
        vi.advanceTimersByTime(PAGE_CONTEXT_RESEND_DEBOUNCE_MS);
      });
      expect(contextCalls()).toHaveLength(2);
      expect((contextCalls()[1][0] as { text: string }).text).toContain(
        'Portfolio',
      );
    } finally {
      main.remove();
    }
  });

  it('does not resend page context while open when the signature is unchanged', async () => {
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
    await act(async () => {
      window.dispatchEvent(new Event('popstate'));
    });
    act(() => {
      vi.advanceTimersByTime(PAGE_CONTEXT_RESEND_DEBOUNCE_MS);
    });
    const pageContextCalls = postMessage.mock.calls.filter(
      ([message]) => (message as { type?: string }).type === DIGICHAT_PAGE_CONTEXT,
    );
    expect(pageContextCalls).toHaveLength(1);
  });

  it('stops sending while closed and sends once again on reopen', () => {
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
    const pageContextCalls = () =>
      postMessage.mock.calls.filter(
        ([message]) =>
          (message as { type?: string }).type === DIGICHAT_PAGE_CONTEXT,
      );
    expect(pageContextCalls()).toHaveLength(1);

    const close = document.body.querySelector(
      '.digichat-launcher__close',
    ) as HTMLButtonElement;
    act(() => close.click());
    act(() => vi.advanceTimersByTime(340));
    expect(pageContextCalls()).toHaveLength(1);

    const reopened = document.body.querySelector(
      '.digichat-launcher__trigger',
    ) as HTMLButtonElement;
    act(() => reopened.click());
    expect(pageContextCalls()).toHaveLength(2);
  });

  it('never sends page context when digichat:ready asks pageContext off', async () => {
    const main = document.createElement('main');
    main.innerHTML = '<h1>House book</h1>';
    document.body.appendChild(main);
    try {
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
            data: { type: DIGICHAT_READY, pageContext: 'off' },
          }),
        );
      });
      act(() => {
        main.innerHTML = '<h1>Portfolio</h1>';
      });
      await act(async () => {});
      act(() => {
        vi.advanceTimersByTime(PAGE_CONTEXT_RESEND_DEBOUNCE_MS);
      });
      const pageContextCalls = postMessage.mock.calls.filter(
        ([message]) =>
          (message as { type?: string }).type === DIGICHAT_PAGE_CONTEXT,
      );
      expect(pageContextCalls).toHaveLength(0);
    } finally {
      main.remove();
    }
  });

  it('renders nothing when config is null', () => {
    act(() => {
      root.render(
        createElement(DigichatPopup, { tier: 'desk', config: null }),
      );
    });
    expect(container.querySelector('[data-digichat-popup]')).toBeNull();
  });

  it('never renders New chat until the host→embed protocol exists (#3785)', () => {
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
    expect(document.body.querySelector('.digichat-launcher__new')).toBeNull();
    expect(document.querySelector('[aria-label="New chat"]')).toBeNull();
  });
});
