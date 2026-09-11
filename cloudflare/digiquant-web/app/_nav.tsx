/** Shared chrome for every digiquant.io page: one brand mark, one nav, one
 *  footer. Keeping these in a single module is what makes the top menu constant
 *  across routes (the prior per-page arrays drifted).
 *
 *  Cross-domain: the header links out to digithings.ai (mirrors digithings.ai's
 *  digiquant.io backlink). Homepage sections use in-page anchors.
 */
import { TerminalMark, type NavLink } from "@digithings/web";

export const DQ_CONTACT_EMAIL = "contact@digiquant.io";

// The terminal lockup: `d` + block cursor, then the wordmark. One inline SVG in
// currentColor, so it follows ink through [data-theme] — this replaces the two
// theme-swapped QR <img>s (a CSS mask proved unreliable here; currentColor does
// not need one). Structurally identical to digithings-web's Brand by intent.
//
// `variant="compact"` deliberately: the full `digi` lockup is five character
// cells wide and closes up below ~64px, well above nav height.
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

export const DQ_FOOTER: NavLink[] = [
  { label: "Pipeline", href: "/#pipeline" },
  { label: "Desk", href: "/#desk" },
  { label: "Strategies", href: "/#strategies" },
  { label: "Pricing", href: "/#pricing" },
  { label: "Changelog", href: "/changelog" },
  { label: "Built on digithings", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DQ_FOOTER_META = "© 2026 digithings AI · open core";
