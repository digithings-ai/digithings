/** Shared chrome for every digiquant.io page. Showcase IA is #4895. */
import { TerminalMark, type NavItem, type NavLink } from "@digithings/ui";
import { SHOWCASE_FOOTER, SHOWCASE_NAV } from "@/lib/showcase";

export const DQ_CONTACT_EMAIL = "contact@digiquant.io";

export const Brand = () => (
  <>
    <TerminalMark size={24} variant="compact" className="hidden max-[880px]:block" />
    <span className="brand-word max-[880px]:hidden">digiquant</span>
  </>
);

export const DQ_NAV_PRIMARY: NavItem[] = SHOWCASE_NAV;
export const DQ_FOOTER: NavLink[] = SHOWCASE_FOOTER;
export const DQ_FOOTER_META = "© 2026 digithings · open core";
