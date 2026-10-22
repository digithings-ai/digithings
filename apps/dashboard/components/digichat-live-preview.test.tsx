/**
 * @vitest-environment happy-dom
 */
import { act, createElement } from 'react';
import { createRoot, type Root } from 'react-dom/client';
import { afterEach, beforeEach, describe, expect, it } from 'vitest';

import DigichatLivePreview from './digichat-live-preview';
import {
  DIGICHAT_POPUP_FRAME_ORIGINS,
  DIGICHAT_UPGRADE_TITLE,
  type DigichatPopupConfig,
} from '@/lib/digichat-popup';
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

describe('DigichatLivePreview', () => {
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

  it('renders the live iframe on an allowed origin for entitled tiers', () => {
    act(() => {
      root.render(
        createElement(DigichatLivePreview, { tier: 'desk', config: CFG }),
      );
    });
    const section = container.querySelector(
      '[data-digichat-live-preview="live"]',
    );
    expect(section).not.toBeNull();
    const iframe = section!.querySelector('iframe');
    expect(iframe).not.toBeNull();
    const origin = new URL(iframe!.getAttribute('src')!).origin;
    expect(DASHBOARD_DIGICHAT_FRAME_SRC).toContain(origin);
    expect(DIGICHAT_POPUP_FRAME_ORIGINS).toContain(origin);
    // Desktop-only: the 300px iframe squeezed <main> to 90px on a 390px
    // phone (measured 22 Oct 2026). Pinned so the phone column cannot
    // regress silently. The inline-style assertion matters too: an inline
    // `display:block` beats Tailwind's `hidden`, and happy-dom does no
    // layout, so the class name alone would not prove the outcome.
    expect(section!.className).toContain('hidden');
    expect(section!.className).toContain('md:block');
    expect(section!.getAttribute('style')).toBeNull();
  });

  it('renders upgrade and no iframe for baseline tiers (#3662)', () => {
    act(() => {
      root.render(
        createElement(DigichatLivePreview, { tier: 'brief', config: CFG }),
      );
    });
    const upgrade = container.querySelector(
      '[data-digichat-live-preview="upgrade"]',
    );
    expect(upgrade).not.toBeNull();
    expect(upgrade!.className).toContain('hidden');
    expect(upgrade!.className).toContain('md:block');
    expect(upgrade!.getAttribute('style')).toBeNull();
    expect(container.querySelector('iframe')).toBeNull();
    expect(container.textContent).toContain(DIGICHAT_UPGRADE_TITLE);
  });
});
