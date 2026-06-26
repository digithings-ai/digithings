/** Shared chrome for every digiquant.io page: one brand mark, one nav, one
 *  footer. Keeping these in a single module is what makes the top menu constant
 *  across routes (the prior per-page arrays drifted).
 *
 *  Cross-domain rule: the *header* never links out to digithings.ai (digiquant
 *  stands on its own); the relationship is surfaced in the footer and on the
 *  architecture/pipeline copy, where "built on the DigiThings stack" belongs.
 */
import { type NavLink } from "@digithings/web";

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

/** v7 nav shape: primary in-site links on the left of the tail, action CTAs on
 *  the right. Route links (not in-page anchors) so the nav resolves from every
 *  page, including `/strategies/<id>`. No "Sign in" (no auth yet). */
export const DQ_NAV_PRIMARY: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" },
  { label: "Strategies", href: "/strategies" },
];

export const DQ_FOOTER: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" },
  { label: "Strategies", href: "/strategies" },
  { label: "Olympus", href: "/olympus/" },
  { label: "Built on DigiThings", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DQ_FOOTER_META = "© 2026 digithings AI · open core";
