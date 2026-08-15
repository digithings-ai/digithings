"use client";

import { useEffect, useRef } from "react";

/**
 * A `mailto:` link to `email`, assigned client-side after mount instead of
 * baked into server-rendered HTML (#2226; same root cause and fix pattern as
 * frontend/digithings-web/components/ContactMailto.tsx, #2220).
 *
 * The embed serves `/embed*` on the digithings.ai zone (and occ.digithings.ai)
 * per frontend/digichat-cloudflare/wrangler.toml -- the same zone confirmed to
 * have Cloudflare's Email Address Obfuscation (Scrape Shield) on. That feature
 * rewrites, at the edge, any literal `mailto:` href AND any bare visible email
 * address text to a `<span class="__cf_email__">`, diverging from what the
 * origin actually sent -- so React's hydration payload (built from the JS
 * bundle, unaware of the edge rewrite) disagrees with the actual DOM. This
 * component (the locked-contact paywall card) renders the address as its own
 * visible link text, the more severe pattern that also triggers the span-wrap
 * rewrite, not just the href rewrite.
 *
 * Rendering with no literal mailto: string or bare address in the initial
 * HTML at all -- inert `href="#"` and a non-address fallback label
 * server-side, the real href and address text assigned after mount -- gives
 * Cloudflare's rewriter nothing to rewrite, so server and client agree. Real
 * users with JS still get a working, address-labeled mailto: link; without JS
 * the link is inert and shows the fallback label instead of the address, the
 * same tradeoff any client-only-assigned href accepts.
 */
export function ContactMailto({
  email,
  className,
  style,
}: {
  email: string;
  className?: string;
  style?: React.CSSProperties;
}) {
  const ref = useRef<HTMLAnchorElement>(null);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;
    el.href = `mailto:${email}`;
    el.textContent = email;
  }, [email]);

  return (
    <a ref={ref} href="#" className={className} style={style}>
      our contact address
    </a>
  );
}
