import { describe, expect, it } from 'vitest';
import {
  buildDigichatEmbedSrc,
  buildPageContextMessage,
  buildThemeMessage,
  canUseDigichatPopup,
  DEFAULT_DIGICHAT_EMBED_HOST,
  DEFAULT_DIGICHAT_EMBED_ORIGIN,
  digichatEmbedOriginForDashboard,
  extractVisiblePageText,
  isDigichatPopupEnabled,
  PAGE_CONTEXT_MAX_CHARS,
  readDigichatPopupConfig,
  readDocumentTheme,
  resolveDigichatEmbedOrigin,
} from './digichat-popup';

describe('canUseDigichatPopup', () => {
  it('is Desk+ only (glass-box / issue “pro+”)', () => {
    expect(canUseDigichatPopup('free')).toBe(false);
    expect(canUseDigichatPopup('brief')).toBe(false);
    expect(canUseDigichatPopup('desk')).toBe(true);
    expect(canUseDigichatPopup('studio')).toBe(true);
    expect(canUseDigichatPopup('enterprise')).toBe(true);
  });
});

describe('resolveDigichatEmbedOrigin', () => {
  it('returns null when unset or invalid', () => {
    expect(resolveDigichatEmbedOrigin({})).toBeNull();
    expect(
      resolveDigichatEmbedOrigin({ NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: 'not a url' }),
    ).toBeNull();
  });

  it('returns absolute origin from env', () => {
    expect(
      resolveDigichatEmbedOrigin({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: 'https://digichat.digithings.ai/embed',
      }),
    ).toBe('https://digichat.digithings.ai');
  });
});

describe('digichatEmbedOriginForDashboard', () => {
  it('falls back to digithings.ai', () => {
    expect(digichatEmbedOriginForDashboard({})).toBe(DEFAULT_DIGICHAT_EMBED_ORIGIN);
  });
});

describe('isDigichatPopupEnabled / readDigichatPopupConfig', () => {
  it('stays off without origin or explicit flag', () => {
    expect(isDigichatPopupEnabled({})).toBe(false);
    expect(readDigichatPopupConfig({})).toBeNull();
  });

  it('stays off when digiquant.io has origin but no token', () => {
    expect(
      isDigichatPopupEnabled({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: 'https://digithings.ai',
      }),
    ).toBe(false);
    expect(
      readDigichatPopupConfig({
        NEXT_PUBLIC_DIGICHAT_POPUP: '1',
      }),
    ).toBeNull();
  });

  it('stays off when ORIGIN is outside CSP frame-src', () => {
    expect(
      isDigichatPopupEnabled({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: 'https://preview.pages.dev',
        NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN: 'tok',
      }),
    ).toBe(false);
  });

  it('enables when origin, CSP, and token are set', () => {
    const env = {
      NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: 'https://digithings.ai',
      NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN: 'tok_test',
    };
    expect(isDigichatPopupEnabled(env)).toBe(true);
    const cfg = readDigichatPopupConfig(env);
    expect(cfg).not.toBeNull();
    expect(cfg!.origin).toBe('https://digithings.ai');
    expect(cfg!.host).toBe(DEFAULT_DIGICHAT_EMBED_HOST);
    expect(cfg!.token).toBe('tok_test');
    expect(cfg!.pageContext).toBe(true);
    expect(cfg!.suggestions.length).toBeGreaterThan(0);
  });

  it('honors POPUP=0 kill switch even with origin + token', () => {
    expect(
      isDigichatPopupEnabled({
        NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: 'https://digithings.ai',
        NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN: 'tok',
        NEXT_PUBLIC_DIGICHAT_POPUP: '0',
      }),
    ).toBe(false);
  });

  it('allows loopback host without token when POPUP=1', () => {
    const cfg = readDigichatPopupConfig({
      NEXT_PUBLIC_DIGICHAT_POPUP: '1',
      NEXT_PUBLIC_DIGICHAT_EMBED_HOST: 'localhost',
    });
    expect(cfg).not.toBeNull();
    expect(cfg!.origin).toBe(DEFAULT_DIGICHAT_EMBED_ORIGIN);
    expect(cfg!.host).toBe('localhost');
    expect(cfg!.token).toBeUndefined();
  });
});

describe('buildDigichatEmbedSrc', () => {
  it('builds compact embed URL with research/portfolio UI params', () => {
    const src = buildDigichatEmbedSrc(
      {
        origin: 'https://digithings.ai',
        host: 'digiquant.io',
        token: 'tok_test',
        mode: 'dot',
        pageContext: true,
        accent: '#3dd6c4',
        welcome: 'hello',
        suggestions: ['a', 'b'],
        placeholder: 'ask…',
      },
      'dark',
    );
    const url = new URL(src);
    expect(url.origin).toBe('https://digithings.ai');
    expect(url.pathname).toBe('/embed');
    expect(url.searchParams.get('host')).toBe('digiquant.io');
    expect(url.searchParams.get('layout')).toBe('embed');
    expect(url.searchParams.get('theme')).toBe('dark');
    expect(url.searchParams.get('token')).toBe('tok_test');
    expect(url.searchParams.get('accent')).toBe('#3dd6c4');
    expect(url.searchParams.get('welcome')).toBe('hello');
    expect(url.searchParams.get('suggestions')).toBe('a|b');
  });
});

describe('page context + theme helpers', () => {
  it('caps visible text', () => {
    const long = 'x'.repeat(PAGE_CONTEXT_MAX_CHARS + 50);
    expect(extractVisiblePageText(PAGE_CONTEXT_MAX_CHARS, long).length).toBe(
      PAGE_CONTEXT_MAX_CHARS,
    );
  });

  it('builds page-context and theme postMessage payloads', () => {
    expect(buildPageContextMessage('hi', undefined, 1)).toEqual({
      type: 'digichat:page-context',
      text: 'hi',
      ts: 1,
    });
    expect(buildThemeMessage('light', 2)).toEqual({
      type: 'digichat:theme',
      theme: 'light',
      ts: 2,
    });
  });

  it('reads document theme from data-theme', () => {
    expect(readDocumentTheme({ getAttribute: () => 'light' })).toBe('light');
    expect(readDocumentTheme({ getAttribute: () => 'dark' })).toBe('dark');
    expect(readDocumentTheme({ getAttribute: () => null })).toBe('dark');
  });
});
