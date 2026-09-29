import { FooterCells, type FooterCell } from "@digithings/ui";

/**
 * Footer cells — the footer as a hairline table rather than a link cloud: one
 * cell per top-level destination at equal weight, separated by the same 1px
 * hairline the rest of the site is drawn with, then a quiet legal strip. No
 * column headings and no nested groups, so the shape cannot drift into a sitemap.
 * This is the digithings.ai footer composition (D1, #4429). Static display
 * template.
 */
const CELLS: FooterCell[] = [
  { label: "GitHub", href: "https://github.com/digithings-ai", external: true },
  { label: "Docs", href: "/docs" },
  { label: "Changelog", href: "/changelog", note: "v2.3.1" },
  { label: "digichat", href: "/chat" },
  { label: "contact@digithings.ai", href: "mailto:contact@digithings.ai" },
];

const META_LINKS = [
  { label: "Privacy", href: "/legal/privacy" },
  { label: "digiquant.io", href: "https://digiquant.io" },
];

export function FooterCellsReference() {
  return (
    <section className="section-block" id="footer-cells">
      <p className="kicker">{"// footer cells"}</p>
      <h2 className="title">Six destinations, one hairline.</h2>
      <p className="section-copy">
        Every top-level destination is one cell of equal weight in a hairline table, and the legal
        strip sits underneath with the copyright, the privacy notice and the sibling site. Nothing
        is grouped, nothing is headed, and the footer never grows a second row of columns.
      </p>
      <div className="mt-[1.2rem] border border-hair border-b-0">
        <FooterCells cells={CELLS} meta="© 2026 digithings · open core" metaLinks={META_LINKS} />
      </div>
    </section>
  );
}
