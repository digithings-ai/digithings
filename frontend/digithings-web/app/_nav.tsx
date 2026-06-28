/** Shared chrome for every digithings.ai page: one brand mark, one nav, one
 *  footer — so the top menu stays constant across routes (the per-page arrays
 *  had drifted, dropping/renaming items between pages).
 *
 *  Cross-domain: the header links out to digiquant.io (the quant product);
 *  digiquant.io intentionally does not link back in its header.
 */
import { type NavLink } from "@digithings/web";

// Transparent, theme-inverted QR mark: near-black modules in light mode,
// white modules in dark mode (no tile/background). CSS shows the one matching
// [data-theme]; two <img>s avoid the Lightning-CSS mask-image drop.
export const Brand = () => (
  <>
    <img src="/favicon-qr-mark-light.svg" alt="" className="brand-mark brand-mark-light" width={26} height={26} aria-hidden="true" />
    <img src="/favicon-qr-mark-dark.svg" alt="" className="brand-mark brand-mark-dark" width={26} height={26} aria-hidden="true" />
    <span className="brand-word">digithings</span>
  </>
);

export const DT_NAV: NavLink[] = [
  { label: "Architecture", href: "/#architecture" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Ask DigiChat", href: "/chat", cta: true },
];

/** v7 nav shape (used by <DigiNav />): wayfinding links on the left of the tail,
 *  action CTAs (theme toggle + GitHub icon + Try Chat) rendered separately on the
 *  right. GitHub lives in the CTA cluster as an icon button, so it is intentionally
 *  omitted here to avoid rendering it twice. */
export const DT_NAV_PRIMARY: NavLink[] = [
  { label: "Architecture", href: "/#architecture" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
];

export const DT_FOOTER: NavLink[] = [
  { label: "Architecture", href: "/#architecture" },
  { label: "DigiChat", href: "/chat" },
  { label: "digiquant.io", href: "https://digiquant.io", external: true },
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
];

export const DT_FOOTER_META = "© 2026 DigiThings · open core";
