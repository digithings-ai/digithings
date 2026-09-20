/**
 * Minimal embed layout.
 *
 * Deliberately does NOT render the authenticated chat shell, sidebar, header,
 * or global Providers. The /embed surface is unauthenticated and designed to
 * be iframed from digithings.ai / digiquant.io. It relies only on:
 *
 *   - the existing `dark` token block from globals.css (same vars Tailwind v4
 *     exposes), and
 *   - a small scoped set of `--accent` overrides keyed by `.accent-*` classes,
 *     applied by the page based on the `?accent=` query param.
 *
 * We import globals.css transitively via the root app layout — Next.js always
 * applies the nearest layout, so this layout composes under the root in the
 * App Router. That keeps Tailwind classnames working without duplicating
 * token definitions here.
 *
 * `dc-embed-shell` is the hook for the readable-measure rule in globals.css:
 * the shell itself stays full-bleed (the tenant background paints edge to
 * edge) and only the `.dc-session` column inside it is capped and centred,
 * exactly as digithings.ai/chat does it.
 */

import type { Metadata } from "next";
import type { ReactNode } from "react";

export const metadata: Metadata = {
  title: "digichat",
  description: "Embedded digichat preview.",
  robots: { index: false, follow: false },
};

export default function EmbedLayout({ children }: { children: ReactNode }) {
  return (
    <div className="dc-embed-shell flex h-dvh w-full flex-col overflow-hidden bg-background text-foreground">
      {/* The embed paints no colour of its own until the page streams the
          tenant's canvas (page.tsx): the root layout's no-JS default is dark,
          and the light `--background` that follows is white — two frames the
          visitor should never see. Stay transparent instead, the same surface
          the attribution strip sits on, so footer and chat space always move
          together; the page replaces this with `--embed-canvas` in the same
          streamed document. `body.bg-background` (0-1-1) beats the root body's
          Tailwind utility (0-1-0); the page's later rule of the same shape
          wins the tie. */}
      <style
        dangerouslySetInnerHTML={{
          __html:
            "html{background:transparent}body.bg-background{background:transparent}.dc-embed-shell{background:transparent}",
        }}
      />
      {children}
    </div>
  );
}
