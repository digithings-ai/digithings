/**
 * Private session chrome: the visible copy a private session shows in place of
 * the tenant's own. A private session presents as a generic support desk, so
 * nothing on screen names the tenant, its product or its ticketing system.
 *
 * Outside a private session the tenant's copy is returned unchanged.
 */

import type { EmbedTenantClientConfig } from "@/lib/embed-client-config";

export const PRIVATE_WELCOME = "Ask about support.";
export const PRIVATE_PLACEHOLDER = "Ask about support";
export const PRIVATE_HEADER_TITLE = "Support";
export const PRIVATE_SUGGESTIONS: readonly string[] = [
  "How do I file a support ticket?",
  "Show my open support tickets",
  "Where can I find the help documentation?",
  "Summarize this week's support tickets",
];

export type ChromeCopy = {
  welcome: string | undefined;
  placeholder: string;
  suggestions: string[];
  headerTitle: string | undefined;
};

export function privateSessionChrome(privateMode: boolean, tenant: ChromeCopy): ChromeCopy {
  if (!privateMode) return tenant;
  return {
    welcome: PRIVATE_WELCOME,
    placeholder: PRIVATE_PLACEHOLDER,
    suggestions: [...PRIVATE_SUGGESTIONS],
    headerTitle: tenant.headerTitle ? PRIVATE_HEADER_TITLE : tenant.headerTitle,
  };
}

/**
 * The tenant config the server hands the first paint of a private page.
 *
 * A `?private=1` page (including a reload of one) for a tenant that opted in
 * to private mode must not carry the tenant's own copy in its initial HTML:
 * the welcome, title, placeholder and suggestion chips name the tenant, and
 * the server-rendered markup and the serialised client props are both in the
 * document before any client code runs. So the server swaps that copy for the
 * generic support-desk copy before rendering, and the browser never receives
 * the tenant's strings for this page.
 *
 * Anything else (theme, gate, models, the opt-in itself) is passed through
 * unchanged. A tenant that did not opt in, or a request without `?private=1`,
 * gets its config back as is, so normal mode keeps the tenant's own copy.
 */
export function privateFirstPaintTenant(
  cfg: EmbedTenantClientConfig,
  urlPrivate: boolean,
): EmbedTenantClientConfig {
  if (!urlPrivate || cfg.privateMode !== true) return cfg;
  return {
    ...cfg,
    title: cfg.title ? PRIVATE_HEADER_TITLE : undefined,
    welcome: PRIVATE_WELCOME,
    welcomeBody: undefined,
    placeholder: PRIVATE_PLACEHOLDER,
    suggestions: [...PRIVATE_SUGGESTIONS],
  };
}

/** `?private=1` exactly, read the same way as `readEmbedUiParams` (first value). */
export function isPrivateUrlParam(value: string | string[] | undefined): boolean {
  return (Array.isArray(value) ? value[0] : value) === "1";
}
