/** Shared chrome for every digithings.ai page: one brand mark, one nav, one
 *  footer — so the top menu stays constant across routes (the per-page arrays
 *  had drifted, dropping/renaming items between pages).
 *
 *  Cross-domain: the header links out to digiquant.io (the quant product);
 *  digiquant.io intentionally does not link back in its header.
 */
import { type NavLink } from "@digithings/web";

export const Brand = () => (
  <>
    <img src="/favicon-qr.svg" alt="" className="brand-mark" width={26} height={26} aria-hidden="true" />
    <span className="brand-word">digithings</span>
  </>
);

export const DT_NAV: NavLink[] = [
  { label: "Architecture", href: "/architecture" },
  { label: "Modules", href: "/#platform" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Try Chat", href: "/chat", cta: true },
];

export const DT_FOOTER: NavLink[] = [
  { label: "Architecture", href: "/architecture" },
  { label: "DigiChat", href: "/chat" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DT_FOOTER_META = "© 2026 DigiThings · open core";
