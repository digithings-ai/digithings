/** Shared chrome for every digiquant.io page: one brand mark, one nav, one
 *  footer. Keeping these in a single module is what makes the top menu constant
 *  across routes (the prior per-page arrays drifted).
 *
 *  Cross-domain: the header links out to digithings.ai (mirrors digithings.ai's
 *  digiquant.io backlink). Homepage sections use in-page anchors.
 */
import { type NavLink } from "@digithings/web";

export const DQ_CONTACT_EMAIL = "contact@digiquant.io";

// Transparent QR marks (no opaque tile): dark modules for light theme, light
// modules for dark theme. CSS shows the one matching [data-theme]. (Two <img>s
// rather than a CSS mask — mask-image proved unreliable here.)
export const Brand = () => (
  <>
    <img src="/favicon-qr-mark-light.svg" alt="" className="brand-mark brand-mark-light" width={24} height={24} aria-hidden="true" />
    <img src="/favicon-qr-mark-dark.svg" alt="" className="brand-mark brand-mark-dark" width={24} height={24} aria-hidden="true" />
    <span className="brand-word">digiquant</span>
  </>
);

/** v7 nav: homepage anchor wayfinding + digithings.ai backlink. Order: Pipeline,
 *  Olympus, Strategies, Pricing. */
export const DQ_NAV_PRIMARY: NavLink[] = [
  { label: "Pipeline", href: "/#pipeline" },
  { label: "Olympus", href: "/#olympus" },
  { label: "Strategies", href: "/#strategies" },
  { label: "Pricing", href: "/#pricing" },
  { label: "digithings.ai", href: "https://digithings.ai", external: true },
];

export const DQ_FOOTER: NavLink[] = [
  { label: "Pipeline", href: "/#pipeline" },
  { label: "Olympus", href: "/#olympus" },
  { label: "Strategies", href: "/#strategies" },
  { label: "Pricing", href: "/#pricing" },
  { label: "Built on digithings", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DQ_FOOTER_META = "© 2026 digithings AI · open core";
