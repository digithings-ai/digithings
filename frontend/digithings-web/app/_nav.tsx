/** Shared chrome for every digithings.ai page: one brand mark, one nav, one
 *  footer — so the top menu stays constant across routes (the per-page arrays
 *  had drifted, dropping/renaming items between pages).
 *
 *  Cross-domain: the header links out to digiquant.io (the quant product);
 *  digiquant.io intentionally does not link back in its header.
 */
import { TerminalMark, type NavItem, type NavLink } from "@digithings/web";

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
    <TerminalMark size={26} variant="compact" className="hidden max-[880px]:block" />
    <span className="brand-word max-[880px]:hidden">digithings</span>
  </>
);

/** v7 nav shape (used by <DtNav />): wayfinding links on the left of the tail,
 *  action CTAs (theme toggle + GitHub icon + Try Chat) rendered separately on the
 *  right. GitHub lives in the CTA cluster as an icon button, so it is intentionally
 *  omitted here to avoid rendering it twice.
 *
 *  Four wayfinding entries, the last a NavGroup: the company pages (About,
 *  Team, Security, Quality) are a small index, not four more top-level slots —
 *  NavShell renders a group as a dropdown on the wide bar and as a labelled
 *  section inside the narrow sheet. "Contact" left the bar with them: it is an
 *  anchor on the home page and it lives in the footer. The website privacy
 *  notice is footer-only by design. */
export const DT_NAV_PRIMARY: NavItem[] = [
  { label: "Docs", href: "/docs" },
  { label: "API", href: "/docs/api" },
  { label: "Architecture", href: "/#architecture" },
  { label: "Services", href: "/services" },
  {
    label: "Company",
    items: [
      { label: "About", href: "/about" },
      { label: "Team", href: "/team" },
      { label: "Security", href: "/security" },
      { label: "Quality", href: "/quality" },
      { label: "Changelog", href: "/changelog" },
    ],
  },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
];

/** Footer stays a flat NavLink[] — <Footer/> takes links, not groups — and it
 *  is where the long tail lives: the company pages and the website privacy
 *  notice. Software use is governed by the repository's MIT licence; paid
 *  services use their own signed agreement, so neither needs generic site
 *  terms. */
export const DT_FOOTER: NavLink[] = [
  { label: "Architecture", href: "/#architecture" },
  { label: "Docs", href: "/docs" },
  { label: "API", href: "/docs/api" },
  { label: "Services", href: "/services" },
  { label: "About", href: "/about" },
  { label: "Team", href: "/team" },
  { label: "Security", href: "/security" },
  { label: "Quality", href: "/quality" },
  { label: "Changelog", href: "/changelog" },
  { label: "Contact", href: "/#contact" },
  { label: "digichat", href: "/chat" },
  { label: "Privacy", href: "/legal/privacy" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DT_FOOTER_META = "© 2026 digithings · open core";
