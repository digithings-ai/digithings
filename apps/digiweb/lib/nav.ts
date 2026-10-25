/**
 * Single source of truth for digiweb's navigation.
 *
 * Both the top bar (`components/site-nav.tsx`) and the home-page contents map
 * (`components/contents-overview.tsx`) read from here, so a surface cannot be
 * listed in one and missing from the other. `/rtl` is a primary entry because
 * it is the standing direction proof (phase 0.2, #4306). The brand pages stay
 * off the primary row in a de-emphasised group: they are local artwork, not
 * the shared language.
 */
export type NavItem = {
  href: string;
  label: string;
  blurb: string;
};

export const PRIMARY_NAV: readonly NavItem[] = [
  {
    href: "/",
    label: "Baseline",
    blurb: "The rules the live surfaces already follow, rendered in their own tile grammar.",
  },
  {
    href: "/foundations",
    label: "Foundations",
    blurb: "Palette roles, type, density and the livery system, read from the tokens.",
  },
  {
    href: "/components",
    label: "Components",
    blurb: "Every kit part, indexed from @digithings/ui — primitives and composites.",
  },
  {
    href: "/rtl",
    label: "RTL",
    blurb: "The whole kit under a dir=ltr/dir=rtl toggle — the direction proof.",
  },
] as const;

/**
 * Reference-only surfaces: kept so the brand work keeps compiling and stays
 * reachable, but deliberately not peers of the language pages — `/brand` is
 * the download kit and `/brand/studio` is the composer.
 */
export const LAB_NAV: readonly NavItem[] = [
  {
    href: "/brand",
    label: "Brand kit",
    blurb: "Avatars, social headers, OG card, mail sign-off — local files only.",
  },
  {
    href: "/brand/studio",
    label: "Brand studio",
    blurb: "Compose the logo and 4×4 wordmark, preview every format, export PNG/SVG.",
  },
] as const;
