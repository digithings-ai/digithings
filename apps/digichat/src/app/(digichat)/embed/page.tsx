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

import { resolveEmbedHostParamOrReferer } from "@/lib/embed-client-config";
import { isEmbedHexColor } from "@/lib/embed-accent-style";
import {
  embedOriginHostOf,
  resolveEmbedClientConfigForPaint,
} from "@/lib/embed-chat-tenant";
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
  const initialTenantCfg = resolveEmbedClientConfigForPaint(
    first(params.token),
    resolveEmbedHostParamOrReferer(first(params.host), referer),
    embedOriginHostOf(hdrs),
  );
  const urlTheme = parseEmbedThemeParam(first(params.theme));
  const paintTheme = urlTheme ?? initialTenantCfg.theme;
  // The host's URL overrides (welcome / placeholder / suggestions / accent)
  // seed the first paint too: the client hook applies them post-mount, which
  // let the generic default copy ("Ask a question") and other unconfigured
  // chrome flash before the configured values landed. Never show a
  // placeholder that is not configured.
  const uiWelcome = first(params.welcome);
  const uiPlaceholder = first(params.placeholder);
  const rawSuggestions = first(params.suggestions);
  const uiSuggestions = rawSuggestions
    ? (() => {
        try {
          const parsed = JSON.parse(rawSuggestions) as unknown;
          if (Array.isArray(parsed)) {
            return parsed.filter(
              (s): s is string => typeof s === "string" && s.trim().length > 0,
            );
          }
        } catch {
          /* fall through to the pipe-separated form */
        }
        return rawSuggestions
          .split("|")
          .map((s) => s.trim())
          .filter(Boolean);
      })()
    : undefined;
  const uiAccent = isEmbedHexColor(first(params.accent))
    ? first(params.accent)
    : undefined;
  const uiAccentForeground = isEmbedHexColor(first(params.accentForeground))
    ? first(params.accentForeground)
    : undefined;
  const themedCfg =
    urlTheme && urlTheme !== initialTenantCfg.theme
      ? { ...initialTenantCfg, theme: urlTheme }
      : initialTenantCfg;
  const seededCfg = {
    ...themedCfg,
    ...(uiWelcome ? { welcome: uiWelcome } : {}),
    ...(uiPlaceholder ? { placeholder: uiPlaceholder } : {}),
    ...(uiSuggestions && uiSuggestions.length
      ? { suggestions: uiSuggestions }
      : {}),
    ...(uiAccent && uiAccentForeground
      ? { accent: { color: uiAccent, foreground: uiAccentForeground } }
      : {}),
  };
  // The canvas walk: the attribution strip is transparent and sits on the
  // shell, while the thread paints its own canvas — two surfaces that must be
  // the same colour from the first byte, not (as they were) white until a
  // post-mount `data-skin-canvas` effect landed. Resolve the one token here,
  // server-side, from what the paint already knows.
  const embedCanvas =
    seededCfg.skin === "digichat"
      ? paintTheme === "dark"
        ? "#121417"
        : "#f1f0eb"
      : "var(--background)";

  return (
    <>
      {/* The app owns its canvas, and it owns exactly ONE of them. The colour
          is resolved server-side (skin + paint theme) into `--embed-canvas`,
          so body, shell, thread and the attribution strip all paint the same
          surface from the first parsed byte — the footer can never flash a
          lighter or darker colour between hydration steps, and a late-landing
          tenant/skin can no longer repaint the shell after the reader is
          looking. The bare baseline view (no host/token) stays fully
          transparent so it is a clean baseline for future work. The host
          iframe is always transparent; the scheme keeps widgets themed. */}
      <style
        dangerouslySetInnerHTML={{
          __html: `html{background:transparent}:root{--embed-canvas:${embedCanvas}}${
            seededCfg.skin === "digichat"
              ? ':root[data-theme="dark"]{--embed-canvas:#121417}:root[data-theme="light"]{--embed-canvas:#f1f0eb}'
              : ""
          }${
            first(params.host) || first(params.token)
              ? "body.bg-background{background:var(--embed-canvas)}.dc-embed-shell{background:var(--embed-canvas)}"
              : "body.bg-background{background:transparent!important}body *{background:transparent!important}"
          }:root[data-embed-wide="1"] body.bg-background{background:transparent}:root[data-embed-wide="1"] .dc-embed-shell{background:transparent}:root[data-theme="dark"] body{color-scheme:dark}:root[data-theme="light"] body{color-scheme:light}`,
        }}
      />
      <script dangerouslySetInnerHTML={{ __html: themePinScript(paintTheme) }} />
      <script
        dangerouslySetInnerHTML={{
          __html:
            "try{document.documentElement.dataset.embedWide=/[?&]wide=1(?:&|$)/.test(window.location.search)?'1':'0';}catch(e){}",
        }}
      />
      <EmbedClient initialTenantCfg={seededCfg} initialBoot={first(params.boot) ?? null} />
    </>
  );
}
