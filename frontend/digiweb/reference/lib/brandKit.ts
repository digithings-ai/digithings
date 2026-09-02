/** Public brand-kit catalogue — hrefs the /brand page renders as downloads.
 *
 *  Served copies live under public/brand/ and are kept in sync by
 *  `frontend/digiweb/brand/build-header.py --check`. Canonical sources stay in
 *  `frontend/digiweb/brand/` so a second hand-copied logo cannot drift.
 */

export const BRAND_WORD = "digithings";
export const BRAND_TAGLINE = "AI infrastructure in a glass box you own.";
export const BRAND_DOMAIN = "digithings.ai";

export type KitFile = {
  label: string;
  href: string;
  size: string;
  note: string;
};

export const AVATARS: KitFile[] = [
  {
    label: "avatar dark 1024",
    href: "/brand/avatar/digithings-avatar-dark.png",
    size: "1024×1024",
    note: "GitHub org, X, LinkedIn company — dark UI",
  },
  {
    label: "avatar light 1024",
    href: "/brand/avatar/digithings-avatar-light.png",
    size: "1024×1024",
    note: "same mark, inverted polarity",
  },
  {
    label: "avatar dark 500",
    href: "/brand/avatar/digithings-avatar-dark-500.png",
    size: "500×500",
    note: "caps at 500px",
  },
  {
    label: "avatar light 500",
    href: "/brand/avatar/digithings-avatar-light-500.png",
    size: "500×500",
    note: "caps at 500px",
  },
  {
    label: "avatar dark svg",
    href: "/brand/avatar/digithings-avatar-dark.svg",
    size: "vector",
    note: "source both PNGs are rendered from",
  },
  {
    label: "avatar light svg",
    href: "/brand/avatar/digithings-avatar-light.svg",
    size: "vector",
    note: "source both PNGs are rendered from",
  },
];

export const HEADERS: KitFile[] = [
  {
    label: "X profile header",
    href: "/brand/headers/digithings-x-1500x500.png",
    size: "1500×500",
    note: "Upload at x.com. Ink is centred inside the crop; the profile photo covers the bottom-left.",
  },
  {
    label: "X profile header svg",
    href: "/brand/headers/digithings-x-1500x500.svg",
    size: "1500×500 vector",
    note: "source for the X PNG",
  },
  {
    label: "LinkedIn personal cover",
    href: "/brand/headers/digithings-linkedin-personal-1584x396.png",
    size: "1584×396",
    note: "Chris's personal upload. LinkedIn crops the sides — keep this file, do not stretch the OG card.",
  },
  {
    label: "LinkedIn personal cover svg",
    href: "/brand/headers/digithings-linkedin-personal-1584x396.svg",
    size: "1584×396 vector",
    note: "source for the personal PNG",
  },
  {
    label: "LinkedIn company cover",
    href: "/brand/headers/digithings-linkedin-company-1128x191.png",
    size: "1128×191",
    note: "Company page banner. Short on purpose; the domain still sits in the stack.",
  },
  {
    label: "LinkedIn company cover svg",
    href: "/brand/headers/digithings-linkedin-company-1128x191.svg",
    size: "1128×191 vector",
    note: "source for the company PNG",
  },
];

export const OG_CARDS: KitFile[] = [
  {
    label: "Open Graph card",
    href: "/og.png",
    size: "1200×630",
    note: "Link unfurls. Also at /brand/og/digithings-og.png.",
  },
  {
    label: "Open Graph card svg",
    href: "/brand/og/digithings-og.svg",
    size: "1200×630 vector",
    note: "source for og.png",
  },
];

export const EMAIL_FILES: KitFile[] = [
  {
    label: "email sign-off plaintext",
    href: "/brand/email/signoff.txt",
    size: "text",
    note: "Company mail footer",
  },
  {
    label: "email sign-off html",
    href: "/brand/email/signoff.html",
    size: "html",
    note: "Inline-styled table for mail clients",
  },
];

export const SIGNOFF_TEXT = `${BRAND_WORD}\n${BRAND_TAGLINE}\nhttps://${BRAND_DOMAIN}\n`;
