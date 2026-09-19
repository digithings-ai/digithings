/**
 * Single source of truth for the reference canon's navigation.
 *
 * Both the top bar (`components/site-nav.tsx`) and the home-page contents map
 * (`components/contents-overview.tsx`) read from here, so a family cannot be
 * listed in one and missing from the other. `/rtl` is a primary entry because
 * it is the standing direction proof (phase 0.2, #4306). `lab/` entries are
 * reference-only (not shipped) and stay off the primary row — they render in a
 * separate, de-emphasised group.
 */
export type NavItem = {
  href: string;
  label: string;
  blurb: string;
};

export const PRIMARY_NAV: readonly NavItem[] = [
  {
    href: "/",
    label: "Foundations",
    blurb: "Livery system, feature picker, button & CTA states.",
  },
  {
    href: "/rtl",
    label: "RTL",
    blurb: "The whole canon under a dir=ltr/dir=rtl toggle — the direction proof.",
  },
  {
    href: "/typography",
    label: "Typography",
    blurb: "Type specimen, scroll-linked word reveals, and the copy & voice grammar.",
  },
  {
    href: "/controls",
    label: "Controls",
    blurb: "Every input and control: buttons, fields, select, menus, tables, overlays.",
  },
  {
    href: "/data",
    label: "Data",
    blurb: "Dot matrix, count-up stats, card deck, repository activity, pricing, matrix.",
  },
  {
    href: "/finance",
    label: "Finance",
    blurb: "Canvas dashboards and the print-grade SVG tearsheet family, screen vs print.",
  },
  {
    href: "/effects",
    label: "Motion",
    blurb: "Cursor-follow graph, terminals, pipeline, ambient mesh, reveals.",
  },
  {
    href: "/chrome",
    label: "Chrome",
    blurb: "Announcement bar, scroll-aware nav, tabs, colophon footer.",
  },
  {
    href: "/chatbot",
    label: "Chat",
    blurb: "Official Thread, thinking chain, composer, markdown, inline chart & graph.",
  },
  {
    href: "/terminal",
    label: "Terminal",
    blurb: "Diegetic CLI session, terminal loaders, and streaming chat transcript.",
  },
  {
    href: "/layout-patterns",
    label: "Layout",
    blurb: "Feature cell, bento grid, numbered stages, scaled product frames.",
  },
  {
    href: "/symbols",
    label: "Symbols",
    blurb: "Module emblems, wordmarks, QR, vendor logos, glyphs.",
  },
  {
    href: "/account",
    label: "Templates",
    blurb: "Login, sign-up, payment, settings, profile page templates.",
  },
] as const;

/**
 * Reference-only surfaces: kept in the canon so they keep compiling and stay
 * available, but deliberately not peers of the shipped families — `/brand` is
 * local artwork and `/iterate` is a working blend lab.
 */
export const LAB_NAV: readonly NavItem[] = [
  {
    href: "/brand",
    label: "Brand",
    blurb: "Avatars, social headers, OG card, mail sign-off — local kit only.",
  },
  {
    href: "/iterate",
    label: "Iterate",
    blurb: "Working blend lab — corners, type, CTAs, heroes. Not product canon.",
  },
] as const;
