import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DocumentFrame } from "./DocumentFrame";
import { GlyphList, GlyphRow } from "./GlyphList";
import { PageTitle } from "./PageTitle";
import { Prose } from "./Prose";
import { Section } from "./Section";

describe("document family", () => {
  it("frames the page between the landing rails, at the rail width", () => {
    const html = renderToStaticMarkup(
      <DocumentFrame>
        <p>body</p>
      </DocumentFrame>,
    );
    expect(html).toContain("line-y line-dashed");
    expect(html).toContain("max-w-[calc(var(--frame-w)+2*var(--page-pad))]");
    expect(html).toContain("overflow-x-clip");
    expect(html).toContain("[counter-reset:doc-section]");
    expect(html).not.toContain("border-x");
  });

  it("separates sections with a full-bleed hairline and numbers the heading", () => {
    const html = renderToStaticMarkup(
      <Section id="modules" title="The modules" lede="Nine ship today.">
        <p>rows</p>
      </Section>,
    );
    expect(html).toContain('id="modules"');
    expect(html).toContain("before:w-screen");
    expect(html).toContain("before:bg-hair");
    expect(html).toContain("px-[var(--page-pad)]");
    expect(html).toContain("[counter-increment:doc-section]");
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

  it("opens a page with a title and one lede, and a path line only when given", () => {
    const bare = renderToStaticMarkup(
      <PageTitle title="Infrastructure, not a product.">
        A set of parts you assemble.
      </PageTitle>,
    );
    expect(bare).toContain("<h1");
    expect(bare).toContain("--type-page-title");
    expect(bare).toContain("A set of parts you assemble.");
    expect(bare).not.toContain("~/digithings");

    const withPath = renderToStaticMarkup(<PageTitle path="services" title="Services" />);
    expect(withPath).toContain("~/digithings/services");
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
