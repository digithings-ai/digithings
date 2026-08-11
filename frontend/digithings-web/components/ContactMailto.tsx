"use client";

import { useEffect, useRef } from "react";
import type { ReactNode } from "react";
import { DT_CONTACT_EMAIL } from "@/app/_nav";

/**
 * A `mailto:` link to DT_CONTACT_EMAIL, assigned client-side after mount
 * instead of baked into server-rendered HTML (#2220).
 *
 * Cloudflare's Email Address Obfuscation (Scrape Shield, on for this zone)
 * rewrites any literal `mailto:` href — and any literal email address in
 * visible text — in the HTML it actually serves: `mailto:x@y.com` becomes
 * `/cdn-cgi/l/email-protection#...`, and a bare `x@y.com` text node gets
 * wrapped in a `<span class="__cf_email__" data-cfemail="...">`. This site's
 * static export bakes the plain mailto: href (and, where the address is
 * shown as the link text, the plain address) into server-rendered HTML, so
 * React's hydration payload disagrees with what Cloudflare actually served
 * — a hydration-mismatch error on every page with a contact link, live-
 * verified by diffing this site's CDN-served HTML against an identical
 * build served without Cloudflare in front of it.
 *
 * Rendering with no literal mailto: string or bare address in the initial
 * HTML at all — an inert `href="#"` server-side, the real href (and,
 * for `showAddress`, the address text) assigned after mount — gives
 * Cloudflare's rewriter nothing to rewrite, so server and client agree.
 * Real users with JS still get a working mailto: link; without JS the link
 * is inert, the same tradeoff any client-only-assigned href accepts.
 */

/** Pure so the query-string assembly is unit-testable without rendering. */
export function buildMailtoHref(email: string, subject?: string): string {
  const query = subject ? `?subject=${subject}` : "";
  return `mailto:${email}${query}`;
}

export function ContactMailto({
  subject,
  className,
  ariaLabel,
  showAddress = false,
  children,
}: {
  /** Appended as `?subject=<subject>` verbatim — callers pass it already
   *  URL-encoded (matching how every call site names its subject today). */
  subject?: string;
  className?: string;
  ariaLabel?: string;
  /** Show DT_CONTACT_EMAIL itself as the link text, set after mount rather
   *  than passed as `children` (which would bake the bare address into the
   *  server-rendered text node, the same problem this component exists to
   *  avoid). Mutually exclusive with `children` in practice — pass one. */
  showAddress?: boolean;
  children?: ReactNode;
}) {
  const ref = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.href = buildMailtoHref(DT_CONTACT_EMAIL, subject);
    if (showAddress) el.textContent = DT_CONTACT_EMAIL;
  }, [subject, showAddress]);

  return (
    <a ref={ref} href="#" className={className} aria-label={ariaLabel}>
      {showAddress ? null : children}
    </a>
  );
}
