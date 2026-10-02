/** Chrome data for every digiquant.io page: brand, nav links, footer sitemap.
 *  The nav is the kit's NavShell and the footer is app/_chrome/Footer.tsx, mounted once in
 *  layout.tsx — this module only supplies content. Homepage sections use
 *  in-page anchors; the header links out to digithings.ai.
 */
import { TerminalMark, type NavLink } from "@digithings/ui";

export const DQ_CONTACT_EMAIL = "contact@digiquant.io";

// `variant="compact"` below the nav breakpoint: the full `digi` lockup closes up
// below ~64px. currentColor, so it follows ink through [data-theme].
export const Brand = () => (
  <>
    <TerminalMark size={24} variant="compact" className="hidden max-[880px]:block" />
    <span className="brand-word max-[880px]:hidden">digiquant</span>
  </>
);

export const DQ_NAV_PRIMARY: NavLink[] = [
  { label: "Dashboard", href: "/#dashboard" },
  { label: "Pipeline", href: "/#pipeline" },
  { label: "Chat", href: "/#chat" },
  { label: "MCP", href: "/#mcp" },
  { label: "Tearsheets", href: "/#tearsheets" },
  { label: "Integrations", href: "/#integrations" },
  { label: "Changelog", href: "/changelog" },
  { label: "digithings.ai", href: "https://digithings.ai", external: true },
];

/** The full map, in labelled columns. The top bar is a short menu; this lists every page,
 *  grouped. Integrations stay out of it: they live only in their own section. */
export const DQ_SITEMAP: { label: string; links: NavLink[] }[] = [
  {
    label: "Showcase",
    links: [
      { label: "Dashboard", href: "/#dashboard" },
      { label: "Pipeline", href: "/#pipeline" },
      { label: "Chat", href: "/#chat" },
    ],
  },
  {
    label: "Tooling",
    links: [
      { label: "MCP", href: "/#mcp" },
      { label: "Tearsheets", href: "/#tearsheets" },
      { label: "Strategies", href: "/strategies" },
    ],
  },
  {
    label: "Start",
    links: [
      { label: "Get started", href: "/#start" },
      { label: "GitHub", href: "https://github.com/digithings-ai/digithings", external: true },
    ],
  },
  {
    label: "Project",
    links: [
      { label: "Changelog", href: "/changelog" },
      { label: "Contact", href: "/contact" },
    ],
  },
  {
    label: "Built on",
    links: [{ label: "digithings", href: "https://digithings.ai", external: true }],
  },
];

export const DQ_FOOTER_META = "© 2026 digithings AI · open core";
