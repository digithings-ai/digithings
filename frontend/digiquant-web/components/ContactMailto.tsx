"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { MouseEvent, ReactNode } from "react";

/**
 * A `mailto:` link assigned client-side after mount instead of baked into
 * server-rendered HTML (#2226; same root cause and fix pattern as
 * frontend/digithings-web/components/ContactMailto.tsx, #2220).
 *
 * Cloudflare's Email Address Obfuscation (Scrape Shield, on for the
 * digiquant.io zone) rewrites any literal `mailto:` href in the HTML it
 * actually serves to `/cdn-cgi/l/email-protection#...`. That diverges from
 * what the origin sent, so React's hydration payload (built from the JS
 * bundle, unaware of the edge rewrite) disagrees with the actual DOM —
 * confirmed live on /contact by diffing the served HTML's `__next_f` flight
 * payload (which still carries the plain `mailto:` string) against the
 * rendered anchor's `href` attribute (rewritten to `/cdn-cgi/...`).
 *
 * Rendering with no literal mailto: string in the initial HTML at all — no
 * href server-side, the real href assigned after client mount — gives
 * Cloudflare's rewriter nothing to rewrite, so server and client agree. Real
 * users with JS still get a working mailto: link; without JS the link is
 * inert, the same tradeoff any client-only-assigned href accepts.
 *
 * Pending look (dimmed, aria-disabled) is derived from a hydration-safe
 * client mount flag (`useSyncExternalStore`) so className / aria-disabled
 * stay synchronized with click prevention — no setState-in-effect and no
 * imperative mutations of React-owned attributes.
 */
const PENDING_CLASSES = ["opacity-50", "cursor-default"] as const;

const emptySubscribe = () => () => {};

export function ContactMailto({
  href,
  className,
  ariaLabel,
  children,
}: {
  /** The full `mailto:...` URI, assigned to the anchor after mount. */
  href: string;
  className?: string;
  ariaLabel?: string;
  children: ReactNode;
}) {
  const mounted = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );

  const onClick = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      if (!mounted) e.preventDefault();
    },
    [mounted],
  );

  return (
    <a
      {...(mounted ? { href } : {})}
      className={[className, ...(!mounted ? PENDING_CLASSES : [])].filter(Boolean).join(" ")}
      aria-label={ariaLabel}
      aria-disabled={mounted ? undefined : true}
      onClick={onClick}
    >
      {children}
    </a>
  );
}
