import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DocumentFrame } from "./DocumentFrame";
import { GlyphList, GlyphRow } from "./GlyphList";
import { PageTitle } from "./PageTitle";
import { Prose } from "./Prose";
import { Section } from "./Section";

describe("document family", () => {
  it("frames the page in a bordered, token-width column", () => {
    const html = renderToStaticMarkup(
      <DocumentFrame>
        <p>body</p>
      </DocumentFrame>,
    );
    expect(html).toContain("max-w-[var(--frame-w)]");
    expect(html).toContain("border-x border-hair");
    expect(html).toContain("max-[1040px]:border-x-0");
  });

  it("separates sections with a hairline and one page step", () => {
    const html = renderToStaticMarkup(
      <Section id="modules" title="The modules" lede="Nine ship today.">
        <p>rows</p>
      </Section>,
    );
    expect(html).toContain('id="modules"');
    expect(html).toContain("border-t border-hair");
    expect(html).toContain("px-[var(--page-pad)]");
    expect(html).toContain("py-[var(--page-step)]");
    expect(html).toContain("first:border-t-0");
    expect(html).toContain("<h2");
    expect(html).toContain("The modules");
    expect(html).toContain("Nine ship today.");
    expect(html).toContain("rows");
  });

  it("renders a section with no heading as a bare hairline block", () => {
    const html = renderToStaticMarkup(
      <Section>
        <p>only</p>
      </Section>,
    );
    expect(html).not.toContain("<h2");
    expect(html).toContain("only");
  });

  it("opens a page with a title and one lede, no eyebrow", () => {
    const html = renderToStaticMarkup(
      <PageTitle title="Infrastructure, not a product.">
        A set of parts you assemble.
      </PageTitle>,
    );
    expect(html).toContain("<h1");
    expect(html).toContain("--type-page-title");
    expect(html).toContain("A set of parts you assemble.");
    expect(html).not.toContain("//");
  });

  it("wraps prose at the measure and leading", () => {
    const html = renderToStaticMarkup(
      <Prose>
        <p>One sentence.</p>
      </Prose>,
    );
    expect(html).toContain("max-w-[var(--measure-prose)]");
    expect(html).toContain("leading-[var(--leading-prose)]");
  });

  it("renders glyph rows as a marker, a bold lead-in and a clause", () => {
    const html = renderToStaticMarkup(
      <GlyphList>
        <GlyphRow label="Self-hosted by default">One compose file.</GlyphRow>
      </GlyphList>,
    );
    expect(html).toContain("[*]");
    expect(html).toContain("<strong");
    expect(html).toContain("Self-hosted by default");
    expect(html).toContain("One compose file.");
    expect(html).toContain("aria-hidden");
  });
});
