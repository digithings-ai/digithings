"use client";

import { useCallback, useEffect, useState } from "react";
import type { MouseEvent, ReactNode } from "react";
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
 * HTML at all — no href server-side, the real href (and, for `showAddress`,
 * the address text) assigned after mount — gives Cloudflare's rewriter
 * nothing to rewrite, so server and client agree. Real users with JS still
 * get a working mailto: link; without JS the link is inert, the same
 * tradeoff any client-only-assigned href accepts.
 *
 * `showAddress` callers must still pass `children` — a non-address fallback
 * ("Email us", "us", …) that server-renders as the link's visible text and
 * accessible name, swapped for the real address once mounted. Server-
 * rendering `showAddress` with no children at all leaves the link visibly
 * empty and unlabeled until JS runs — a discernible-text regression, not
 * the documented "inert without JS" tradeoff above.
 *
 * Pending look (dimmed, aria-disabled) is driven from React state so
 * className / aria-disabled stay synchronized with click prevention.
 */

/** Pure so the query-string assembly is unit-testable without rendering. */
export function buildMailtoHref(email: string, subject?: string): string {
  const query = subject ? `?subject=${subject}` : "";
  return `mailto:${email}${query}`;
}

// Baked into the JSX unconditionally rather than a new app-local CSS class —
// the frontend canon guard's family census (#1421) rejects a new class in a
// census app's stylesheet; token-backed Tailwind utilities are not scanned.
const PENDING_CLASSES = ["opacity-50", "cursor-default"] as const;

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
  /** Swap `children` for DT_CONTACT_EMAIL itself once mounted, rather than
   *  passing the address as `children` directly (which would bake the bare
   *  address into the server-rendered text node — the same problem this
   *  component exists to avoid). `children` is still required: it's the
   *  server-rendered fallback text and accessible name until the swap. */
  showAddress?: boolean;
  children?: ReactNode;
}) {
  const [readyHref, setReadyHref] = useState<string | null>(null);
  const [addressText, setAddressText] = useState<string | null>(null);

  useEffect(() => {
    setReadyHref(buildMailtoHref(DT_CONTACT_EMAIL, subject));
    if (showAddress) setAddressText(DT_CONTACT_EMAIL);
  }, [subject, showAddress]);

  const pending = readyHref === null;
  const onClick = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      if (pending) e.preventDefault();
    },
    [pending],
  );

  return (
    <a
      {...(readyHref ? { href: readyHref } : {})}
      className={[className, ...(pending ? PENDING_CLASSES : [])].filter(Boolean).join(" ")}
      aria-label={ariaLabel}
      aria-disabled={pending ? true : undefined}
      onClick={onClick}
    >
      {addressText ?? children}
    </a>
  );
}
