/** Shared chrome for every digithings.ai page: one brand mark, one nav, one
 *  footer — so the top menu stays constant across routes (the per-page arrays
 *  had drifted, dropping/renaming items between pages).
 *
 *  Cross-domain: the header links out to digiquant.io (the quant product);
 *  digiquant.io intentionally does not link back in its header.
 */
import { TerminalMark, type NavLink } from "@digithings/web";

export const DT_CONTACT_EMAIL = "contact@digithings.ai";

// The terminal lockup: `d` + block cursor, then the wordmark. One inline SVG in
// currentColor, so it follows ink through [data-theme] — this replaces the two
// theme-swapped QR <img>s (a single recolorable mark was unreliable there because
// Lightning CSS drops mask-image; currentColor has no such problem).
//
// `variant="compact"` deliberately: the full `digi` lockup is five character
// cells wide and closes up below ~64px, well above nav height. NavShell already
// wraps this in <a aria-label="digithings home">, so the mark stays decorative.
export const Brand = () => (
  <>
    <TerminalMark size={26} variant="compact" />
    <span className="brand-word">digithings</span>
  </>
);

/** v7 nav shape (used by <DtNav />): wayfinding links on the left of the tail,
 *  action CTAs (theme toggle + GitHub icon + Try Chat) rendered separately on the
 *  right. GitHub lives in the CTA cluster as an icon button, so it is intentionally
 *  omitted here to avoid rendering it twice. */
export const DT_NAV_PRIMARY: NavLink[] = [
  { label: "Architecture", href: "/#architecture" },
  { label: "Docs", href: "/docs" },
  { label: "Contact", href: "/#contact" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
];

export const DT_FOOTER: NavLink[] = [
  { label: "Architecture", href: "/#architecture" },
  { label: "Docs", href: "/docs" },
  { label: "Contact", href: "/#contact" },
  { label: "digichat", href: "/chat" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DT_FOOTER_META = "© 2026 digithings · open core";
