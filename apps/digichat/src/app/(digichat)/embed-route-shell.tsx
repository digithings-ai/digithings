/**
 * Embed route shell (single-route plan, Step 3).
 *
 * Server-side tenant verify + first-paint seeding, shared by `/embed` and
 * `/?mode=embed` so both serve byte-identical HTML. The tenant is knowable
 * before a single byte is painted (`token`/`host` are already in the URL),
 * which removes the dark→light flash a client-only resolve would cause.
 * Reading `headers()` opts consumers into dynamic rendering, which is
 * correct and required: the response varies per tenant token, so a cached
 * or prerendered copy would serve one tenant's theme to another. It also
 * owns the `dc-embed-shell` wrapper div and the transparent first-paint
 * style (moved from `app/(digichat)/embed/layout.tsx` so the `?mode=embed`
 * rewrite serves byte-identical HTML).
 */

import { resolveEmbedHostParamOrReferer } from "@/lib/embed-client-config";
import {
  embedOriginHostOf,
  resolveEmbedClientConfigForPaint,
} from "@/lib/embed-chat-tenant";
import { resolveEmbedSeededTenant } from "@/lib/route-client-config";
import { headers } from "next/headers";
import EmbedClient from "./embed/embed-client";

/* Pre-paint theme pin for the embed document. Runs after the root layout's
   head scripts so it deliberately wins over them; mirrors [data-theme] onto
   the .dark/.light classes. No value from the request is interpolated into
   these strings — the two scripts are complete literals selected by a
   boolean, so there is no concatenation path for request data to reach the
   document. */
const THEME_PIN_SCRIPTS = {
  light:
    "try{var e=document.documentElement;e.setAttribute('data-theme','light');e.classList.add('light');e.classList.remove('dark')}catch(t){}",
  dark: "try{var e=document.documentElement;e.setAttribute('data-theme','dark');e.classList.add('dark');e.classList.remove('light')}catch(t){}",
} as const;

function themePinScript(theme: "dark" | "light"): string {
  return theme === "light" ? THEME_PIN_SCRIPTS.light : THEME_PIN_SCRIPTS.dark;
}

const first = (value: string | string[] | undefined): string | undefined =>
  Array.isArray(value) ? value[0] : value;

export default async function EmbedRouteShell({
  params,
}: {
  params: Record<string, string | string[] | undefined>;
}) {
  const hdrs = await headers();
  const referer = hdrs.get("referer") ?? hdrs.get("referrer");
  const initialTenantCfg = resolveEmbedClientConfigForPaint(
    first(params.token),
    resolveEmbedHostParamOrReferer(first(params.host), referer),
    embedOriginHostOf(hdrs),
  );
  const { seeded: seededCfg, urlTheme } = resolveEmbedSeededTenant(
    initialTenantCfg,
    params,
  );
  const paintTheme = urlTheme ?? initialTenantCfg.theme;
  // The host's URL overrides (welcome / placeholder / suggestions / accent)
  // seed the first paint too: the client hook applies them post-mount, which
  // let the generic default copy ("Ask a question") and other unconfigured
  // chrome flash before the configured values landed. Never show a
  // placeholder that is not configured.

  // The canvas walk: the attribution strip is transparent and sits on the
  // shell, while the thread paints its own canvas — two surfaces that must be
  // the same colour from the first byte, not (as they were) white until a
  // post-mount `data-skin-canvas` effect landed. Resolve the one token here,
  // server-side, from what the paint already knows.
  const embedCanvas =
    seededCfg.skin === "digichat"
      ? paintTheme === "dark"
        ? "#121417" // canon-allow: the first parsed byte has no CSS var to read yet
        : "#f1f0eb" // canon-allow: same literal pair as the product-chrome.css term-bg fallback
      : "var(--background)";

  return (
    <div className="dc-embed-shell flex h-dvh w-full flex-col overflow-hidden bg-background text-foreground">
      {/* The embed paints no colour of its own until the canvas below streams
          the tenant's surface (moved verbatim from `app/(digichat)/embed/layout.tsx`):
          the root layout's no-JS default is dark, and the light `--background`
          that follows is white — two frames the visitor should never see. Stay
          transparent instead, the same surface the attribution strip sits on, so
          footer and chat space always move together; the canvas rule below
          replaces this in the same streamed document. `body.bg-background`
          (0-1-1) beats the root body's Tailwind utility (0-1-0); the canvas
          rule's later rule of the same shape wins the tie. */}
      <style
        dangerouslySetInnerHTML={{
          __html:
            "html{background:transparent}body.bg-background{background:transparent}.dc-embed-shell{background:transparent}",
        }}
      />
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
              ? ':root[data-theme="dark"]{--embed-canvas:#121417}:root[data-theme="light"]{--embed-canvas:#f1f0eb}' // canon-allow: keeps the canvas token correct when the theme flips before hydration
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
    </div>
  );
}
