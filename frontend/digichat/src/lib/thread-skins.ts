/**
 * Official assistant-ui templates a digichat container can pick at deploy time.
 *
 * Ids 1–11 match assistant-ui `list_templates`. `digichat` is the first-party
 * Thread — the gallery `/chatbot` module at `@digithings/web/chat/thread`
 * (`thread.aui.tsx` + slots + cube glyphs), not a catalog clone.
 * `base` is the fixed Base demo. `base-assistant-ui` is the configurable
 * Base shell (brandTheme + labels). Same Thread, different catalog product.
 *
 * They are vendored in the image — not a CDN switch and not shadcn styles.
 */

export const THREAD_SKINS = [
  "base",
  "chatgpt",
  "claude",
  "grok",
  "gemini",
  "perplexity",
  "react-ink",
  "expo-react-native",
  "base-assistant-ui",
  "webpage-assistant",
  "product-page-assistant",
  "digichat",
] as const;

export type ThreadSkin = (typeof THREAD_SKINS)[number];

export const DEFAULT_THREAD_SKIN: ThreadSkin = "base";

/** First-party marketing / OCC hosts. Unset `skin` → `digichat`, not catalog `base`. */
export const FIRST_PARTY_DEFAULT_SKIN_HOSTS: ReadonlySet<string> = new Set([
  "digithings.ai",
  "www.digithings.ai",
  "occ.digithings.ai",
]);

export const FIRST_PARTY_DEFAULT_SKIN_SLUGS: ReadonlySet<string> = new Set([
  "digithings",
  "digithings-ai",
  "occ",
]);

/**
 * Runtime default for a tenant host/slug when YAML / DIGICHAT_EMBED_TENANTS
 * omit `skin`. Third-party tenants stay on catalog `base`. Explicit `skin`
 * must still win at the call site.
 */
export function defaultThreadSkinForTenant(opts: {
  host?: string | null;
  slug?: string | null;
  aliases?: readonly string[] | null;
}): ThreadSkin {
  const hosts = [opts.host, ...(opts.aliases ?? [])];
  for (const raw of hosts) {
    const host = raw?.trim().toLowerCase().split("/")[0].split(":")[0].replace(/\.$/, "");
    if (host && FIRST_PARTY_DEFAULT_SKIN_HOSTS.has(host)) return "digichat";
  }
  const slug = opts.slug?.trim().toLowerCase();
  if (slug && FIRST_PARTY_DEFAULT_SKIN_SLUGS.has(slug)) return "digichat";
  return DEFAULT_THREAD_SKIN;
}

export const CLONE_SKINS = [
  "chatgpt",
  "claude",
  "grok",
  "gemini",
  "perplexity",
] as const;

export type CloneSkin = (typeof CLONE_SKINS)[number];

/**
 * Catalog templates that own the viewport (docs shell, product dashboard,
 * Expo phone frame). Host chrome (ChatShell CLI, embed header, memory
 * sidebar) must not wrap these — the template is the page.
 */
export const LAYOUT_SKINS = [
  "webpage-assistant",
  "product-page-assistant",
  "expo-react-native",
] as const;

export type LayoutSkin = (typeof LAYOUT_SKINS)[number];

export function threadSkinChoices(): string {
  return THREAD_SKINS.join(", ");
}

export function isThreadSkin(value: unknown): value is ThreadSkin {
  return typeof value === "string" && (THREAD_SKINS as readonly string[]).includes(value);
}

export function isCloneSkin(value: ThreadSkin): value is CloneSkin {
  return (CLONE_SKINS as readonly string[]).includes(value);
}

export function skinOwnsPageChrome(value: ThreadSkin): boolean {
  return (LAYOUT_SKINS as readonly string[]).includes(value);
}

/** Parse a query/env/YAML value; unknown → default. */
export function parseThreadSkin(
  value: string | null | undefined,
  fallback: ThreadSkin = DEFAULT_THREAD_SKIN,
): ThreadSkin {
  const trimmed = value?.trim().toLowerCase();
  return isThreadSkin(trimmed) ? trimmed : fallback;
}
