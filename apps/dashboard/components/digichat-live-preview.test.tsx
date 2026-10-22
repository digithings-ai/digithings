/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';

import DigichatLivePreview from './digichat-live-preview';
import {
  DIGICHAT_POPUP_FRAME_ORIGINS,
  DIGICHAT_READY,
  DIGICHAT_UPGRADE_TITLE,
  type DigichatPopupConfig,
  type PlanTier,
} from '@/lib/digichat-popup';
import { AuthContext, type AuthContextValue } from '@/lib/auth-context';
import { DASHBOARD_DIGICHAT_FRAME_SRC } from '@/lib/security-headers';

(globalThis as { IS_REACT_ACT_ENVIRONMENT?: boolean }).IS_REACT_ACT_ENVIRONMENT = true;

const CFG: DigichatPopupConfig = {
  origin: 'https://digichat.digithings.ai',
  host: 'digiquant.io',
  mode: 'dot',
  pageContext: false,
  accent: '#3dd6c4',
  welcome: '',
  suggestions: [],
  placeholder: 'ask…',
};

const TOKEN = 'session-access-token';

function authWithToken(
  token: string | null,
  authEnabled = true,
): AuthContextValue {
  return {
    authEnabled,
    loading: false,
    user: null,
    session: token ? ({ access_token: token } as never) : null,
    signInWithOAuth: async () => {},
    signInWithPassword: async () => {},
    signUpWithPassword: async () => {},
    signOut: async () => {},
  } satisfies AuthContextValue;
}

/**
 * The width utilities of a class list. Exact, not a substring: `w-full` and
 * `w-max` in the same list would both satisfy `toContain('w-full')`, and
 * `w-max`/`min-w-[900px]` is exactly how the column gets squeezed again.
 */
function widthUtilities(className: string): string[] {
  return className
    .split(/\s+/)
    .filter((token) => /^(min-|max-)?w-/.test(token));
}

/**
 * The `contentWindow` descriptor as the prototype chain defines it, so the
 * test can put it back exactly as it found it.
 */
function findContentWindowDescriptor(): {
  owner: object;
  descriptor: PropertyDescriptor;
} | null {
  let owner: object | null = HTMLIFrameElement.prototype;
  while (owner) {
    const descriptor = Object.getOwnPropertyDescriptor(owner, 'contentWindow');
    if (descriptor) return { owner, descriptor };
    owner = Object.getPrototypeOf(owner);
  }
  return null;
}

describe('DigichatLivePreview', () => {
  let container: HTMLDivElement;
  let root: Root;
  let postMessage: ReturnType<typeof vi.fn>;
  /** The frame's window. Stable, so a message can name it as its source. */
  let frameWindow: { postMessage: ReturnType<typeof vi.fn> };
  let originalContentWindow: {
    owner: object;
    descriptor: PropertyDescriptor;
  } | null;

  /** A `digichat:ready` message from the given origin, sent by this frame. */
  function readyEvent(origin: string, source: unknown = frameWindow): MessageEvent {
    const event = new MessageEvent('message', {
      data: { type: DIGICHAT_READY },
    });
    Object.defineProperty(event, 'origin', { value: origin });
    Object.defineProperty(event, 'source', { value: source });
    return event;
  }

  /** A message from the given origin that is **not** a ready. */
  function otherEvent(origin: string, type: string): MessageEvent {
    const event = new MessageEvent('message', { data: { type } });
    Object.defineProperty(event, 'origin', { value: origin });
    Object.defineProperty(event, 'source', { value: frameWindow });
    return event;
  }

  beforeEach(() => {
    container = document.createElement('div');
    document.body.appendChild(container);
    root = createRoot(container);
    document.documentElement.setAttribute('data-theme', 'dark');
    // The frame's window is mocked **before** the component mounts, so a post
    // that happens at mount time (instead of after `digichat:ready`) is seen.
    postMessage = vi.fn();
    frameWindow = { postMessage };
    originalContentWindow = findContentWindowDescriptor();
    Object.defineProperty(HTMLIFrameElement.prototype, 'contentWindow', {
      configurable: true,
      get: () => frameWindow,
    });
  });

  afterEach(() => {
    act(() => {
      root.unmount();
    });
    container.remove();
    if (originalContentWindow) {
      Object.defineProperty(
        originalContentWindow.owner,
        'contentWindow',
        originalContentWindow.descriptor,
      );
    }
  });

  function render(
    tier: PlanTier,
    opts: { token?: string | null; authEnabled?: boolean } = {},
  ) {
    act(() => {
      root.render(
        createElement(
          AuthContext.Provider,
          {
            value: authWithToken(
              opts.token ?? null,
              opts.authEnabled ?? true,
            ),
          },
          createElement(DigichatLivePreview, { tier, config: CFG }),
        ),
      );
    });
  }

  /** Open the strip: the embed mounts on the first open. */
  function openPreview() {
    const summary = container.querySelector('summary');
    expect(summary).not.toBeNull();
    act(() => {
      summary!.dispatchEvent(
        new MouseEvent('click', { bubbles: true, cancelable: true }),
      );
    });
  }

  it('renders the live iframe on an allowed origin for entitled tiers', () => {
    render('desk', { token: TOKEN });
    openPreview();
    const section = container.querySelector(
      '[data-digichat-live-preview="live"]',
    );
    expect(section).not.toBeNull();
    const iframe = section!.querySelector('iframe');
    expect(iframe).not.toBeNull();
    const origin = new URL(iframe!.getAttribute('src')!).origin;
    expect(DASHBOARD_DIGICHAT_FRAME_SRC).toContain(origin);
    expect(DIGICHAT_POPUP_FRAME_ORIGINS).toContain(origin);
  });

  it('does not mount the embed before the strip is opened', () => {
    render('desk', { token: TOKEN });
    // A frame inside a closed <details> still loads, so an eager iframe would
    // boot the whole digichat app on every dashboard route.
    expect(container.querySelector('iframe')).toBeNull();
    openPreview();
    expect(container.querySelector('iframe')).not.toBeNull();
  });

  it('keeps the strip bounded to the content column (DIG-5138)', () => {
    render('desk', { token: TOKEN });
    const section = container.querySelector(
      '[data-digichat-live-preview="live"]',
    )!;
    // w-full: the strip takes the width of the column it lives in, never a
    // max-content width of its own. As a row sibling of <main> it took the
    // upgrade paragraph's width and squeezed the page column to 38px.
    expect(widthUtilities(section.className)).toEqual(['w-full']);
    expect(section.getAttribute('style')).toBeNull();
  });

  it('sizes the embed explicitly instead of the browser default 300x150', () => {
    render('desk', { token: TOKEN });
    openPreview();
    const iframe = container.querySelector('iframe')!;
    // The embed is a chat surface: it never stretches over the whole column.
    expect(widthUtilities(iframe.className)).toEqual([
      'w-full',
      'max-w-[640px]',
    ]);
    expect(iframe.className).toContain('h-[320px]');
    expect(iframe.className).toContain('md:h-[480px]');
    expect(iframe.getAttribute('style')).toBeNull();
  });

  it('ships the strip collapsed so the page is not pushed down', () => {
    render('desk', { token: TOKEN });
    const details = container.querySelector('details')!;
    expect(details.hasAttribute('open')).toBe(false);
  });

  it('renders upgrade and no iframe for baseline tiers (#3662)', () => {
    render('brief');
    const upgrade = container.querySelector(
      '[data-digichat-live-preview="upgrade"]',
    );
    expect(upgrade).not.toBeNull();
    expect(widthUtilities(upgrade!.className)).toEqual(['w-full']);
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.textContent).toContain(DIGICHAT_UPGRADE_TITLE);
  });

  it('carries no session material into the upgrade branch', () => {
    render('brief', { token: TOKEN });
    // The upgrade branch is for a tier that may not chat; it must not leak
    // the session token into the DOM.
    expect(container.innerHTML).not.toContain(TOKEN);
  });

  it('renders nothing for an entitled tier without a session', () => {
    // Without a session the embed never gets a plan proof and every turn
    // answers 403 plan_tier_required: a dead chat surface. Fail closed.
    render('desk');
    expect(container.innerHTML).toBe('');
  });

  it('mirrors the popup in the classic shell, which has no sessions', () => {
    // Auth off: the dashboard models the user as entitled and the popup
    // shows the embed. The preview shows the same surface instead of
    // inventing a third behaviour for it.
    render('desk', { authEnabled: false });
    openPreview();
    expect(container.querySelector('iframe')).not.toBeNull();
  });

  it('posts nothing to the frame before the embed reports ready', () => {
    render('desk', { token: TOKEN });
    openPreview();
    // The session token must not leave the page until the embed asks for it.
    expect(postMessage).not.toHaveBeenCalled();
  });

  it('posts the plan tier to the embed for entitled tiers (DIG-5139)', () => {
    render('desk', { token: TOKEN });
    openPreview();

    act(() => {
      window.dispatchEvent(readyEvent(CFG.origin));
    });

    const planTierCall = postMessage.mock.calls.find(
      ([message]) => (message as { type?: string })?.type === 'digichat:plan-tier',
    );
    expect(planTierCall).toBeTruthy();
    expect(planTierCall![0]).toMatchObject({
      type: 'digichat:plan-tier',
      tier: 'desk',
      accessToken: TOKEN,
    });
    expect(planTierCall![1]).toBe(CFG.origin);
    // The theme message comes first, exactly as the popup sends it.
    expect((postMessage.mock.calls[0][0] as { type?: string }).type).toBe(
      'digichat:theme',
    );
    // Exactly one handshake per ready: the embed mints one proof per ready,
    // so a doubled message list would mint two.
    expect(postMessage).toHaveBeenCalledTimes(2);
  });

  it('tells the embed which theme the dashboard runs in', () => {
    render('desk', { token: TOKEN });
    openPreview();

    act(() => {
      window.dispatchEvent(readyEvent(CFG.origin));
    });

    const themeCall = postMessage.mock.calls.find(
      ([message]) => (message as { type?: string })?.type === 'digichat:theme',
    );
    expect(themeCall).toBeTruthy();
    expect((themeCall![0] as { theme?: string }).theme).toBe('dark');
  });

  it('sends the session tier, not a fixed one, in the plan-tier proof', () => {
    render('studio', { token: TOKEN });
    openPreview();

    act(() => {
      window.dispatchEvent(readyEvent(CFG.origin));
    });

    const planTierCall = postMessage.mock.calls.find(
      ([message]) => (message as { type?: string })?.type === 'digichat:plan-tier',
    );
    expect(planTierCall).toBeTruthy();
    expect((planTierCall![0] as { tier?: string }).tier).toBe('studio');
  });

  it('sends the plan tier once the session token arrives', () => {
    render('desk');
    // No session yet: the live arm does not render at all.
    expect(container.innerHTML).toBe('');

    // The session arrives later; the next ready carries the proof.
    render('desk', { token: TOKEN });
    openPreview();
    postMessage.mockClear();
    act(() => {
      window.dispatchEvent(readyEvent(CFG.origin));
    });
    const planTierCall = postMessage.mock.calls.find(
      ([message]) => (message as { type?: string })?.type === 'digichat:plan-tier',
    );
    expect(planTierCall).toBeTruthy();
    expect(planTierCall![0]).toMatchObject({
      tier: 'desk',
      accessToken: TOKEN,
    });
  });

  it('ignores a ready message from another origin', () => {
    render('desk', { token: TOKEN });
    openPreview();

    act(() => {
      window.dispatchEvent(readyEvent('https://evil.example'));
    });

    expect(postMessage).not.toHaveBeenCalled();
  });

  it('ignores a ready message from an origin that only looks like the embed', () => {
    render('desk', { token: TOKEN });
    openPreview();

    act(() => {
      window.dispatchEvent(
        readyEvent('https://digichat.digithings.ai.attacker.example'),
      );
    });

    expect(postMessage).not.toHaveBeenCalled();
  });

  it('ignores a message from the embed origin that is not a ready', () => {
    render('desk', { token: TOKEN });
    openPreview();

    act(() => {
      window.dispatchEvent(otherEvent(CFG.origin, 'digichat:page-context'));
    });

    expect(postMessage).not.toHaveBeenCalled();
  });

  it('ignores a ready from another frame on the embed origin', () => {
    render('desk', { token: TOKEN });
    openPreview();

    // The DigiChat popup is on the same origin. Its ready must not mint a
    // second proof in this frame.
    act(() => {
      window.dispatchEvent(
        readyEvent(CFG.origin, { postMessage: vi.fn() } as never),
      );
    });

    expect(postMessage).not.toHaveBeenCalled();
  });

  it('sends no handshake to a baseline tier (no frame, no proof)', () => {
    render('brief', { token: TOKEN });
    // No frame means no proof: the baseline branch never renders an iframe,
    // so there is nothing to talk to.
    expect(container.querySelector('iframe')).toBeNull();
  });
});
