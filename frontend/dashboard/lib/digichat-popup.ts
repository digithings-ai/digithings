/**
 * digichat popup embed for the digiquant dashboard (#3422 / #3581).
 *
 * Desk+ (plan “pro” in the issue = Desk / glass-box) get a bottom-right launcher
 * that iframes digichat `/embed?layout=embed` — same popup contract as digichat
 * `widget.js` (#3421), implemented in-React so CSP stays `script-src 'self'`.
 *
 * Grounding, web search, three-tier models, and digigraph→digillm live in the
 * digichat tenant registry (`DIGICHAT_EMBED_TENANTS` for digiquant.io) — not here.
 */

import {
  extractPageContext as extractPageContextShared,
  extractPageHtml as extractPageHtmlShared,
  sanitizePageHtml as sanitizePageHtmlShared,
} from '../../digichat/src/lib/page-context-sanitize'; // canonical allowlist (#3602)
import { can, type PlanTier } from './entitlements';

export type { PlanTier };

/** Production digichat origin when env is unset (Containers on digithings.ai). */
export const DEFAULT_DIGICHAT_EMBED_ORIGIN = 'https://digithings.ai';

/** Registry host key for digiquant.io /dashboard embeds. */
export const DEFAULT_DIGICHAT_EMBED_HOST = 'digiquant.io';

/**
 * Origins allowed by dashboard CSP `frame-src` (see security-headers.mjs).
 * Keep in sync — popup fails closed when ORIGIN is outside this set.
 */
export const DIGICHAT_POPUP_FRAME_ORIGINS: readonly string[] = [
  'https://digithings.ai',
  'https://www.digithings.ai',
  'https://digichat.digithings.ai',
  'http://127.0.0.1:3005',
  'http://localhost:3005',
];

/** digiquant phosphor for embed `?accent=` — digichat URL requires #rrggbb. */
export const DIGICHAT_POPUP_ACCENT = '#3dd6c4'; // canon-allow: digichat ?accent= embed URL

export const DIGICHAT_READY = 'digichat:ready';
export const DIGICHAT_PAGE_CONTEXT = 'digichat:page-context';
export const DIGICHAT_THEME = 'digichat:theme';

/** Keep in sync with digichat `DEFAULT_POPUP_PAGE_CONTEXT_MAX_CHARS`. */
export const PAGE_CONTEXT_MAX_CHARS = 8_000;

/**
 * Sanitized HTML snapshot cap. Keep in sync with digichat
 * `MAX_PAGE_CONTEXT_HTML_CHARS` — larger than text so structure survives.
 */
export const PAGE_CONTEXT_HTML_MAX_CHARS = 12_000;

/** Launcher label matches digithings-web desktop CTA (`DtNav` / `.dc-nav-cta`). */
export const DIGICHAT_LAUNCHER_LABEL = 'ask digichat';

/** Open-state launcher label — same control toggles close / minimize. */
export const DIGICHAT_LAUNCHER_CLOSE_LABEL = 'close';

export type DigichatPopupTheme = 'light' | 'dark';

export type DigichatPopupConfig = {
  origin: string;
  host: string;
  token?: string;
  /** Always rectangular “ask digichat” chrome (#3581); `dot` kept for env back-compat. */
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
 * Direct `process.env.NEXT_PUBLIC_*` reads so Turbopack/Next can compile-time
 * inline them into the client bundle (same pattern as `lib/supabase.ts`).
 * Passing whole `process.env` and indexing `env.NEXT_PUBLIC_*` does **not**
 * get inlined — SSR then shows the launcher and hydration removes it (#3561).
 */
export function digichatPopupEnvFromProcess(): Record<string, string | undefined> {
  return {
    NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN: process.env.NEXT_PUBLIC_DIGICHAT_EMBED_ORIGIN,
    NEXT_PUBLIC_DIGICHAT_EMBED_HOST: process.env.NEXT_PUBLIC_DIGICHAT_EMBED_HOST,
    NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN: process.env.NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN,
    NEXT_PUBLIC_DIGICHAT_POPUP: process.env.NEXT_PUBLIC_DIGICHAT_POPUP,
    NEXT_PUBLIC_DIGICHAT_POPUP_MODE: process.env.NEXT_PUBLIC_DIGICHAT_POPUP_MODE,
    NEXT_PUBLIC_DIGICHAT_PAGE_CONTEXT: process.env.NEXT_PUBLIC_DIGICHAT_PAGE_CONTEXT,
  };
}

/**
 * @returns absolute origin, or null if unset/invalid
 */
export function resolveDigichatEmbedOrigin(
  env: Record<string, string | undefined> = digichatPopupEnvFromProcess(),
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
  env: Record<string, string | undefined> = digichatPopupEnvFromProcess(),
): string {
  return resolveDigichatEmbedOrigin(env) ?? DEFAULT_DIGICHAT_EMBED_ORIGIN;
}

/** True when origin is listed in dashboard CSP frame-src. */
export function isDigichatOriginAllowedByCsp(origin: string): boolean {
  return (DIGICHAT_POPUP_FRAME_ORIGINS as readonly string[]).includes(origin);
}

/**
 * digiquant.io (and any non-loopback host) needs an embed token — digichat
 * treats only digithings.ai hosts as first-party for tokenless embed.
 */
export function embedHostRequiresToken(host: string): boolean {
  const h = host.trim().toLowerCase();
  if (!h) return true;
  if (h === 'localhost' || h === '127.0.0.1' || h === '[::1]') return false;
  if (h === 'digithings.ai' || h === 'www.digithings.ai' || h === 'occ.digithings.ai') {
    return false;
  }
  return true;
}

/**
 * Opt-in popup: requires ORIGIN (or POPUP=1) and fails closed when the
 * resolved origin is outside CSP frame-src, or when the host needs a token
 * and none is configured (avoids a wrong-tenant gated embed).
 */
export function isDigichatPopupEnabled(
  env: Record<string, string | undefined> = digichatPopupEnvFromProcess(),
): boolean {
  if (env.NEXT_PUBLIC_DIGICHAT_POPUP === '0') return false;
  const wants =
    env.NEXT_PUBLIC_DIGICHAT_POPUP === '1' ||
    Boolean(resolveDigichatEmbedOrigin(env));
  if (!wants) return false;
  const origin = digichatEmbedOriginForDashboard(env);
  if (!isDigichatOriginAllowedByCsp(origin)) return false;
  const host =
    env.NEXT_PUBLIC_DIGICHAT_EMBED_HOST?.trim() || DEFAULT_DIGICHAT_EMBED_HOST;
  const token = env.NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN?.trim();
  if (embedHostRequiresToken(host) && !token) return false;
  return true;
}

export function readDigichatPopupConfig(
  env: Record<string, string | undefined> = digichatPopupEnvFromProcess(),
): DigichatPopupConfig | null {
  if (!isDigichatPopupEnabled(env)) return null;
  const origin = digichatEmbedOriginForDashboard(env);
  const host =
    env.NEXT_PUBLIC_DIGICHAT_EMBED_HOST?.trim() || DEFAULT_DIGICHAT_EMBED_HOST;
  const token = env.NEXT_PUBLIC_DIGICHAT_EMBED_TOKEN?.trim() || undefined;
  // Default rectangular “ask digichat” chrome (#3581). Opt into legacy round
  // launcher only with POPUP_MODE=dot.
  const mode =
    env.NEXT_PUBLIC_DIGICHAT_POPUP_MODE?.trim().toLowerCase() === 'dot'
      ? 'dot'
      : 'bar';
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
  bodyText?: string | null,
): string {
  if (bodyText !== undefined) {
    return (bodyText ?? '').replace(/\s+/g, ' ').trim().slice(0, maxChars);
  }
  return extractPageContextShared(undefined, PAGE_CONTEXT_HTML_MAX_CHARS, maxChars).text;
}

/** Structural allowlist — same walk as digichat `page-context-sanitize.ts`. */
export function sanitizePageHtml(
  raw: string,
  maxChars = PAGE_CONTEXT_HTML_MAX_CHARS,
): string {
  return sanitizePageHtmlShared(raw, maxChars);
}

export function extractPageContext(
  maxHtml = PAGE_CONTEXT_HTML_MAX_CHARS,
  maxText = PAGE_CONTEXT_MAX_CHARS,
): { html: string; text: string } {
  return extractPageContextShared(undefined, maxHtml, maxText);
}

/**
 * Prefer `main` / `[role=main]`, else `body`. Live computed-style walk so
 * CSS-hidden nodes never enter the payload (#3602).
 */
export function extractPageHtml(
  maxChars = PAGE_CONTEXT_HTML_MAX_CHARS,
  doc: Document | null | undefined =
    typeof document !== 'undefined' ? document : null,
): string {
  return extractPageHtmlShared(maxChars, doc ?? null);
}

export function buildPageContextMessage(
  text: string,
  opts?: {
    html?: string;
    screenshotDataUrl?: string;
    ts?: number;
  },
): {
  type: typeof DIGICHAT_PAGE_CONTEXT;
  text: string;
  ts: number;
  html?: string;
  screenshotDataUrl?: string;
} {
  const ts = opts?.ts ?? Date.now();
  const payload: {
    type: typeof DIGICHAT_PAGE_CONTEXT;
    text: string;
    ts: number;
    html?: string;
    screenshotDataUrl?: string;
  } = { type: DIGICHAT_PAGE_CONTEXT, text, ts };
  const htmlRaw = opts?.html?.trim();
  if (htmlRaw) {
    const html = sanitizePageHtml(htmlRaw, PAGE_CONTEXT_HTML_MAX_CHARS);
    if (html) payload.html = html;
  }
  if (opts?.screenshotDataUrl) payload.screenshotDataUrl = opts.screenshotDataUrl;
  return payload;
}

export function buildThemeMessage(
  theme: DigichatPopupTheme,
  ts = Date.now(),
): { type: typeof DIGICHAT_THEME; theme: DigichatPopupTheme; ts: number } {
  return { type: DIGICHAT_THEME, theme, ts };
}
