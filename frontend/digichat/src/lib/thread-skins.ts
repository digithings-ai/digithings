/**
 * Official assistant-ui templates a digichat container can pick at deploy time.
 *
 * Ids 1–11 match assistant-ui `list_templates`. `digichat` is the first-party
 * Thread (digiweb tokens + primitives) — not a catalog clone.
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
