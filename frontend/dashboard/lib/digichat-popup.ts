/**
 * digichat popup embed for the digiquant dashboard (#3422).
 *
 * Desk+ (plan “pro” in the issue = Desk / glass-box) get a bottom-right launcher
 * that iframes digichat `/embed?layout=embed` — same popup contract as digichat
 * `widget.js` (#3421), implemented in-React so CSP stays `script-src 'self'`.
 *
 * Grounding, web search, three-tier models, and DigiGraph→DigiLLM live in the
 * digichat tenant registry (`DIGICHAT_EMBED_TENANTS` for digiquant.io) — not here.
 */

import { can, type PlanTier } from './entitlements';

export type { PlanTier };

/** Production digichat origin when env is unset (Containers on digithings.ai). */
export const DEFAULT_DIGICHAT_EMBED_ORIGIN = 'https://digithings.ai';

/** Registry host key for digiquant.io /dashboard embeds. */
export const DEFAULT_DIGICHAT_EMBED_HOST = 'digiquant.io';

/** Digiquant phosphor — matches `--accent-digiquant` (dark). */
export const DIGICHAT_POPUP_ACCENT = '#3dd6c4';

export const DIGICHAT_READY = 'digichat:ready';
export const DIGICHAT_PAGE_CONTEXT = 'digichat:page-context';
export const DIGICHAT_THEME = 'digichat:theme';

/** Keep in sync with digichat `DEFAULT_POPUP_PAGE_CONTEXT_MAX_CHARS`. */
export const PAGE_CONTEXT_MAX_CHARS = 8_000;

export type DigichatPopupTheme = 'light' | 'dark';

export type DigichatPopupConfig = {
  origin: string;
  host: string;
  token?: string;
  mode: 'dot' | 'bar';
  pageContext: boolean;
  accent: string;
  welcome: string;
  suggestions: string[];
  placeholder: string;
};

const RESEARCH_PORTFOLIO_WELCOME =
  'Ask about house research, portfolio decisions, and the page you are on.';

const RESEARCH_PORTFOLIO_SUGGESTIONS = [
  'What changed in the house book?',
  "Summarize today's research digest",
  'Why is this position sized this way?',
] as const;

/**
 * Desk+ unlocks glass-box research + portfolio deliberation — the issue’s
 * “pro and above, not basic” gate (Brief alone is not enough).
 */
export function canUseDigichatPopup(tier: PlanTier): boolean {
  return can(tier, 'glassbox_economics');
}

/**
 * @returns absolute origin, or null if unset/invalid
 */
export function resolveDigichatEmbedOrigin(
  env: Record<string, string | undefined> = process.env as Record<
    string,
    string | undefined
  >,
): string | null {
  const raw = env.NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN?.trim();
  if (!raw) return null;
  try {
    const origin = new URL(raw).origin;
    if (origin.startsWith('http://') || origin.startsWith('https://')) return origin;
    return null;
  } catch {
    return null;
  }
}

/** Origin for iframe + CSP: env when valid, else production default. */
export function digichatEmbedOriginForDashboard(
  env: Record<string, string | undefined> = process.env as Record<
    string,
    string | undefined
  >,
): string {
  return resolveDigichatEmbedOrigin(env) ?? DEFAULT_DIGICHAT_EMBED_ORIGIN;
}

/**
 * Opt-in popup: requires an explicit enable flag so digiquant.io does not
 * mount a broken launcher before digichat tenant ops are ready.
 */
export function isDigichatPopupEnabled(
  env: Record<string, string | undefined> = process.env as Record<
    string,
    string | undefined
  >,
): boolean {
  if (env.NEXT_PUBLIC_DIGICHAT_POPUP === '0') return false;
  if (env.NEXT_PUBLIC_DIGICHAT_POPUP === '1') return true;
  // Origin alone is enough when operators set the embed origin on Pages.
  return Boolean(resolveDigichatEmbedOrigin(env));
}

export function readDigichatPopupConfig(
  env: Record<string, string | undefined> = process.env as Record<
    string,
    string | undefined
  >,
): DigichatPopupConfig | null {
  if (!isDigichatPopupEnabled(env)) return null;
  const origin = digichatEmbedOriginForDashboard(env);
  const host =
    env.NEXT_PUBLIC_DIGICHAT_EMBED_HOST?.trim() || DEFAULT_DIGICHAT_EMBED_HOST;
  const token = env.NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN?.trim() || undefined;
  const mode =
    env.NEXT_PUBLIC_DIGICHAT_POPUP_MODE?.trim().toLowerCase() === 'bar'
      ? 'bar'
      : 'dot';
  const pageContext = env.NEXT_PUBLIC_DIGICHAT_PAGE_CONTEXT !== '0';
  return {
    origin,
    host,
    token,
    mode,
    pageContext,
    accent: DIGICHAT_POPUP_ACCENT,
    welcome: RESEARCH_PORTFOLIO_WELCOME,
    suggestions: [...RESEARCH_PORTFOLIO_SUGGESTIONS],
    placeholder: 'ask about research or portfolio…',
  };
}

export function buildDigichatEmbedSrc(
  cfg: DigichatPopupConfig,
  theme: DigichatPopupTheme,
): string {
  const url = new URL(`${cfg.origin.replace(/\/$/, '')}/embed`);
  url.searchParams.set('host', cfg.host);
  url.searchParams.set('layout', 'embed');
  url.searchParams.set('theme', theme);
  url.searchParams.set('accent', cfg.accent);
  if (cfg.token) url.searchParams.set('token', cfg.token);
  if (cfg.welcome) url.searchParams.set('welcome', cfg.welcome);
  if (cfg.placeholder) url.searchParams.set('placeholder', cfg.placeholder);
  if (cfg.suggestions.length) {
    url.searchParams.set('suggestions', cfg.suggestions.join('|'));
  }
  return url.toString();
}

export function readDocumentTheme(
  el: { getAttribute(name: string): string | null } = typeof document !==
  'undefined'
    ? document.documentElement
    : { getAttribute: () => null },
): DigichatPopupTheme {
  return el.getAttribute('data-theme') === 'light' ? 'light' : 'dark';
}

export function extractVisiblePageText(
  maxChars = PAGE_CONTEXT_MAX_CHARS,
  bodyText: string | null | undefined =
    typeof document !== 'undefined' ? document.body?.innerText : '',
): string {
  return (bodyText ?? '').replace(/\s+/g, ' ').trim().slice(0, maxChars);
}

export function buildPageContextMessage(
  text: string,
  screenshotDataUrl?: string,
  ts = Date.now(),
): {
  type: typeof DIGICHAT_PAGE_CONTEXT;
  text: string;
  ts: number;
  screenshotDataUrl?: string;
} {
  const payload: {
    type: typeof DIGICHAT_PAGE_CONTEXT;
    text: string;
    ts: number;
    screenshotDataUrl?: string;
  } = { type: DIGICHAT_PAGE_CONTEXT, text, ts };
  if (screenshotDataUrl) payload.screenshotDataUrl = screenshotDataUrl;
  return payload;
}

export function buildThemeMessage(
  theme: DigichatPopupTheme,
  ts = Date.now(),
): { type: typeof DIGICHAT_THEME; theme: DigichatPopupTheme; ts: number } {
  return { type: DIGICHAT_THEME, theme, ts };
}
