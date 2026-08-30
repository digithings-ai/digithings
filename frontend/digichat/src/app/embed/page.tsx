/**
 * /embed — server shell. Resolves the tenant's presentation from the iframe
 * URL's own params so the FIRST paint is already the tenant's, then hands the
 * interactive surface to embed-client.tsx.
 *
 * Why this file exists at all: the client tree can only learn its tenant by
 * fetching /api/embed/tenant-config after mount, and until that resolves it
 * necessarily renders the gated defaults — dark theme, default digichat accent.
 * For a light-themed tenant that painted the whole embed dark for a
 * round-trip and then flipped, a visible dark→light flash on every load. The
 * root layout hardcodes `data-theme="dark"` as its no-JS default (layout.tsx),
 * so the flash started in the SSR HTML itself and no client-side change could
 * remove it.
 *
 * `token` and `host` are already in the URL the server is answering, so the
 * tenant is knowable here, before a single byte is painted. The pre-paint
 * script below re-points <html data-theme> the same way the root layout's own
 * themeInitScript does, and `initialTenantCfg` seeds the client hook so it
 * starts where the fetch would have landed instead of at the dark defaults.
 *
 * Reading `searchParams` opts this route into dynamic rendering, which is
 * correct and required: the response varies per tenant token, so a cached or
 * prerendered copy would serve one tenant's theme to another. `force-dynamic`
 * states that intent rather than leaving it to inference — the failure mode if
 * it were ever inferred wrong is silent (#1379 was exactly that class of bug).
 */

import { resolveEmbedClientConfigFromParams, resolveEmbedHostParamOrReferer } from "@/lib/embed-client-config";
import { parseEmbedThemeParam } from "@/lib/embed-theme-messages";
import { headers } from "next/headers";
import EmbedClient from "./embed-client";

export const dynamic = "force-dynamic";

/** Pre-paint theme pin for the embed document.
 *
 * Runs after the root layout's head scripts, so it deliberately wins over
 * them: themeInitScript resolves `dt-theme`/prefers-color-scheme, neither of
 * which an anonymous embed visitor has any say in, and a tenant that asked for
 * `light` must not inherit the visitor's OS dark mode. Mirrors [data-theme]
 * onto the .dark/.light classes for the Tailwind `dark:` variant, same rule as
 * themeClassSyncScript — keep the three in lockstep.
 *
 * Optional `?theme=light|dark` (parent shell sync) overrides the registry theme
 * for first paint so digithings.ai `/chat` matches the marketing site mode.
 *
 * No value from the request is interpolated into this string. The two scripts
 * are complete literals selected by a boolean, so even a registry entry that
 * somehow carried an unexpected `theme` can only pick one of them — there is
 * no concatenation path for request data to reach the document.
 *
 * Soft client-side navigations do not execute scripts inserted via
 * `dangerouslySetInnerHTML`; production embeds are always a fresh document
 * load, so the pin applies on first paint only — theme after in-app routing
 * comes from the client hook, not this script. */
const THEME_PIN_SCRIPTS = {
  light:
    "try{var e=document.documentElement;e.setAttribute('data-theme','light');e.classList.add('light');e.classList.remove('dark')}catch(t){}",
  dark: "try{var e=document.documentElement;e.setAttribute('data-theme','dark');e.classList.add('dark');e.classList.remove('light')}catch(t){}",
} as const;

function themePinScript(theme: "dark" | "light"): string {
  return theme === "light" ? THEME_PIN_SCRIPTS.light : THEME_PIN_SCRIPTS.dark;
}

export default async function EmbedPage({
  searchParams,
}: {
  searchParams: Promise<Record<string, string | string[] | undefined>>;
}) {
  const params = await searchParams;
  const hdrs = await headers();
  const referer = hdrs.get("referer") ?? hdrs.get("referrer");
  const first = (value: string | string[] | undefined): string | undefined =>
    Array.isArray(value) ? value[0] : value;
  const initialTenantCfg = resolveEmbedClientConfigFromParams(
    first(params.token),
    resolveEmbedHostParamOrReferer(first(params.host), referer),
  );
  const urlTheme = parseEmbedThemeParam(first(params.theme));
  const paintTheme = urlTheme ?? initialTenantCfg.theme;
  const seededCfg =
    urlTheme && urlTheme !== initialTenantCfg.theme
      ? { ...initialTenantCfg, theme: urlTheme }
      : initialTenantCfg;

  return (
    <>
      <script dangerouslySetInnerHTML={{ __html: themePinScript(paintTheme) }} />
      <EmbedClient initialTenantCfg={seededCfg} />
    </>
  );
}
