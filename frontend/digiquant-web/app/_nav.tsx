/** Shared chrome for every digiquant.io page: one brand mark, one nav, one
 *  footer. Keeping these in a single module is what makes the top menu constant
 *  across routes (the prior per-page arrays drifted).
 *
 *  Cross-domain rule: the *header* never links out to digithings.ai (digiquant
 *  stands on its own); the relationship is surfaced in the footer and on the
 *  architecture/pipeline copy, where "built on the DigiThings stack" belongs.
 */
import { type NavLink } from "@digithings/web";

export const Brand = () => (
  <>
    <img src="/favicon-qr.svg" alt="" className="brand-mark" width={26} height={26} aria-hidden="true" />
    <span className="brand-word">digiquant</span>
  </>
);

export const DQ_NAV: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" },
  { label: "Strategies", href: "/strategies" },
  { label: "Pricing", href: "/#pricing" },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Open Olympus", href: "/olympus/", cta: true },
];

export const DQ_FOOTER: NavLink[] = [
  { label: "Pipeline", href: "/pipeline" },
  { label: "Strategies", href: "/strategies" },
  { label: "Olympus", href: "/olympus/" },
  { label: "Built on DigiThings", href: "https://digithings.ai", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DQ_FOOTER_META = "© 2026 digithings AI · open core";
