/** Chrome data for every digiquant.io page: brand, nav links, footer cells.
 *  The chrome itself is the kit's NavShell + FooterCells, mounted once in
 *  layout.tsx — this module only supplies content. Homepage sections use
 *  in-page anchors; the header links out to digithings.ai.
 */
import { TerminalMark, type FooterCell, type NavLink } from "@digithings/ui";

export const DQ_CONTACT_EMAIL = "contact@digiquant.io";

// `variant="compact"` below the nav breakpoint: the full `digi` lockup closes up
// below ~64px. currentColor, so it follows ink through [data-theme].
export const Brand = () => (
  <>
    <TerminalMark size={24} variant="compact" className="hidden max-[880px]:block" />
    <span className="brand-word max-[880px]:hidden">digiquant</span>
  </>
);

export const DQ_NAV_PRIMARY: NavLink[] = [
  { label: "Pipeline", href: "/#pipeline" },
  { label: "Desk", href: "/#desk" },
  { label: "Strategies", href: "/#strategies" },
  { label: "Pricing", href: "/#pricing" },
  { label: "Changelog", href: "/changelog" },
  { label: "digithings.ai", href: "https://digithings.ai", external: true },
];

export const DQ_FOOTER_CELLS: FooterCell[] = [
  { label: "Strategies", href: "/strategies" },
  { label: "Pricing", href: "/#pricing" },
  { label: "Changelog", href: "/changelog" },
  { label: "Built on digithings", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DQ_FOOTER_META = "© 2026 digithings AI · open core";
