/**
 * ContactMailto — the shared Cloudflare-safe `mailto:` link, promoted from
 * the three forks that grew one per app (`frontend/digithings-web`,
 * `frontend/digiquant-web`, `frontend/digichat`, issues #2220/#2226).
 *
 * Cloudflare's Email Address Obfuscation (Scrape Shield) rewrites any
 * literal `mailto:` href — and any bare visible address — in the HTML it
 * actually serves, so React's hydration payload disagrees with the real DOM.
 * This component renders with no literal `mailto:` string or bare address in
 * the initial HTML at all (no href server-side; the real href — and, for
 * `showAddress`, the address text — assigned after the hydration-safe client
 * mount flag flips), giving the edge rewriter nothing to rewrite.
 *
 * Real users with JS get a working mailto: link; without JS the link is
 * inert (dimmed, aria-disabled). `showAddress` callers must still pass
 * `children` — the server-rendered fallback text and accessible name until
 * the mount swap. Omitting `children` entirely leaves the link empty until
 * JS runs: acceptable only on JS-required surfaces (the digichat embed),
 * never on static marketing pages.
 *
 * Utility-classed (pending dim only); consuming apps need an `@source` line
 * for this directory (MIGRATION.md rule 3).
 */
"use client";

import { useCallback, useSyncExternalStore } from "react";
import type { CSSProperties, MouseEvent, ReactNode } from "react";

import { cx } from "../controls/cx";

/** Pure so the query-string assembly is unit-testable without rendering. */
export function buildMailtoHref(email: string, subject?: string): string {
  const query = subject ? `?subject=${subject}` : "";
  return `mailto:${email}${query}`;
}

// Baked into the JSX unconditionally rather than a new app-local CSS class —
// the frontend canon guard's family census rejects new classes in census
// app stylesheets; token-backed Tailwind utilities are not scanned.
const PENDING_CLASSES = ["opacity-50", "cursor-default"] as const;

const emptySubscribe = () => () => {};
const getMountedSnapshot = () => true;
const getServerSnapshot = () => false;

export function ContactMailto({
  email,
  subject,
  showAddress = false,
  className,
  style,
  ariaLabel,
  children,
}: {
  /** Appended as `?subject=<subject>` verbatim — callers pass it already
   *  URL-encoded. */
  email: string;
  subject?: string;
  /** Swap `children` for the address itself once mounted, rather than
   *  passing the address as `children` directly (which would bake the bare
   *  address into the server-rendered text node). `children` is still
   *  required on static pages: the fallback text and accessible name. */
  showAddress?: boolean;
  className?: string;
  style?: CSSProperties;
  ariaLabel?: string;
  children?: ReactNode;
}) {
  // Server + first client hydration pass: false. After hydration: true.
  // useSyncExternalStore, not setState-in-effect.
  const mounted = useSyncExternalStore(
    emptySubscribe,
    getMountedSnapshot,
    getServerSnapshot,
  );

  if (
    process.env.NODE_ENV !== "production" &&
    showAddress &&
    children == null
  ) {
    // eslint-disable-next-line no-console
    console.warn(
      "ContactMailto with showAddress and no children renders an empty, " +
        "unlabeled link until JS runs — pass fallback children on static pages.",
    );
  }

  const readyHref = mounted ? buildMailtoHref(email, subject) : null;
  const addressText = mounted && showAddress ? email : null;
  const pending = !mounted;

  const onClick = useCallback(
    (e: MouseEvent<HTMLAnchorElement>) => {
      if (pending) e.preventDefault();
    },
    [pending],
  );

  return (
    <a
      {...(readyHref ? { href: readyHref } : {})}
      className={cx(className, pending && PENDING_CLASSES.join(" "))}
      style={style}
      aria-label={ariaLabel}
      aria-disabled={pending ? true : undefined}
      onClick={onClick}
    >
      {addressText ?? children}
    </a>
  );
}
