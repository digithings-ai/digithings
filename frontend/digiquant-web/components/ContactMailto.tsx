"use client";

import { useCallback, useEffect, useRef } from "react";
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
 * Rendering with no literal mailto: string in the initial HTML at all — an
 * inert `href="#"` server-side, the real href assigned after mount — gives
 * Cloudflare's rewriter nothing to rewrite, so server and client agree.
 * Real users with JS still get a working mailto: link; without JS the link
 * is inert, the same tradeoff any client-only-assigned href accepts.
 *
 * WCAG 9 fix (full-UI-suite critique, digiquant-web target): pre-wiring the
 * link looked IDENTICAL to a working one — a click before the effect below
 * runs (slow connection, or permanently for a no-JS visitor) silently
 * scrolled to "#" with zero feedback, on the page's two actual revenue CTAs.
 * The pending look (dimmed, aria-disabled) is baked into the JSX below
 * unconditionally, in token-backed Tailwind utilities rather than a new
 * app-local CSS class (the frontend canon guard's family census, #1421,
 * rejects a hand-rolled class in a census app's stylesheet) — the effect
 * clears it by mutating the mounted DOM node directly, the same imperative-
 * after-mount escape hatch already used for `href` two lines below. That
 * keeps this a single render with no state to resync: since the JSX always
 * describes the SAME initial (pending) attributes, React never re-applies
 * them on a later reconciliation and the imperative clear-out sticks.
 */
const PENDING_CLASSES = ["opacity-50", "cursor-default"] as const;

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
  const ref = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.href = href;
    el.classList.remove(...PENDING_CLASSES);
    el.removeAttribute("aria-disabled");
  }, [href]);

  // Reads the live DOM rather than component state, so it keeps swallowing
  // clicks exactly until the effect above clears aria-disabled -- no state
  // to fall out of sync with the imperative DOM mutation.
  const onClick = useCallback((e: MouseEvent<HTMLAnchorElement>) => {
    if (ref.current?.getAttribute("aria-disabled") === "true") e.preventDefault();
  }, []);

  return (
    <a
      ref={ref}
      href="#"
      className={[className, ...PENDING_CLASSES].filter(Boolean).join(" ")}
      aria-label={ariaLabel}
      aria-disabled="true"
      onClick={onClick}
    >
      {children}
    </a>
  );
}
