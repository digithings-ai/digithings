/** Shared chrome for every digithings.ai page: one brand mark, one nav, one
 *  footer — so the top menu stays constant across routes (the per-page arrays
 *  had drifted, dropping/renaming items between pages).
 *
 *  Cross-domain: the header links out to digiquant.io (the quant product);
 *  digiquant.io intentionally does not link back in its header.
 */
import { TerminalMark, type NavItem, type NavLink } from "@digithings/ui";

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
 *  Team, Security, Changelog) are a small index, not four more top-level slots —
 *  NavShell renders a group as a dropdown on the wide bar and as a labelled
 *  section inside the narrow sheet. Nothing here points back into a band of
 *  the home page — the landing's own section rail does that wayfinding. The
 *  website privacy notice is footer-only by design. */
export const DT_NAV_PRIMARY: NavItem[] = [
  { label: "Docs", href: "/docs" },
  { label: "API", href: "/docs/api" },
  { label: "Wiki", href: "/openwiki" },
  { label: "Services", href: "/services" },
  {
    label: "Company",
    items: [
      { label: "About", href: "/about" },
      { label: "Team", href: "/team" },
      { label: "Security", href: "/security" },
      { label: "Changelog", href: "/changelog" },
    ],
  },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
];

/** One row of boxes. None of these are the top-bar links (Docs, API, Wiki,
 *  Services, the company menu, digiquant.io, the GitHub icon, or ask digichat). */
export const DT_FOOTER_BOXES: NavLink[] = [
  { label: "Contact", href: `mailto:${DT_CONTACT_EMAIL}` },
  { label: "Privacy", href: "/legal/privacy" },
  { label: "X", href: "https://x.com/digithingsai", external: true },
  { label: "LinkedIn", href: "https://www.linkedin.com/company/digithingsai/", external: true },
];

/** The full map, in gloom-style columns. The top bar is a short menu; this is
 *  where every page is listed, grouped. Live is the running products. */
export const DT_SITEMAP: { label: string; links: NavLink[] }[] = [
  {
    label: "Live",
    links: [
      { label: "digichat", href: "/chat" },
      { label: "digiquant", href: "https://digiquant.io", external: true },
      { label: "dashboard", href: "https://digiquant.io/dashboard/", external: true },
    ],
  },
  {
    label: "Product",
    links: [
      { label: "Docs", href: "/docs" },
      { label: "API", href: "/docs/api" },
      { label: "Wiki", href: "/openwiki" },
      { label: "Services", href: "/services" },
    ],
  },
  {
    label: "Company",
    links: [
      { label: "About", href: "/about" },
      { label: "Team", href: "/team" },
      { label: "Security", href: "/security" },
      { label: "Changelog", href: "/changelog" },
    ],
  },
  {
    label: "Connect",
    links: [
      { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
      { label: DT_CONTACT_EMAIL, href: `mailto:${DT_CONTACT_EMAIL}` },
    ],
  },
  {
    label: "Legal",
    links: [{ label: "Privacy", href: "/legal/privacy" }],
  },
];

export const DT_FOOTER_META = "© 2026 digithings · open core";
