/** Shared chrome for every digithings.ai page: one brand mark, one nav, one
 *  footer — so the top menu stays constant across routes (the per-page arrays
 *  had drifted, dropping/renaming items between pages).
 *
 *  Cross-domain: the header links out to digiquant.io (the quant product);
 *  digiquant.io intentionally does not link back in its header.
 */
import { type NavItem, type NavLink } from "@digithings/ui";
import { DIGITHINGS } from "@digithings/hero-banner/definitions";
import { ScrollBanner } from "@/components/landing/ScrollBanner";

export const DT_CONTACT_EMAIL = "contact@digithings.ai";

// The DIGITHINGS hero banner, armed at mount and kept live. It is on screen at
// scroll 0, and it replays LOADING with the landing hero on every visit instead
// of skipping to the settled mark after the first play in the tab.
export const Brand = () => (
  <ScrollBanner
    def={DIGITHINGS}
    inView={false}
    replayLoading
    className="w-[8.5rem] max-[880px]:w-[7rem]"
  />
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
