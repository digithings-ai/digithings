import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DotMatrix } from "./DotMatrix";

describe("DotMatrix accessible name", () => {
  it("exposes the label as aria-label on the img role", () => {
    const html = renderToStaticMarkup(<DotMatrix state="success" label="Ok" />);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="Ok"');
  });

  it("falls back to the state name when no label is given", () => {
    const html = renderToStaticMarkup(<DotMatrix state="newChat" />);
    expect(html).toContain('role="img"');
    expect(html).toContain('aria-label="newChat"');
  });

  // DIG-4669: the label used to live twice — once as the aria-label and once
  // in an sr-only span inside the img role. The role makes its children
  // presentational, so the second copy was never announced and only gave the
  // next maintainer a second place to change the name.
  it("carries the name in one place only", () => {
    const html = renderToStaticMarkup(<DotMatrix state="success" label="Ok" />);
    expect(html).not.toContain("sr-only");
  });

  it("renders a decorative glyph with no name at all", () => {
    const html = renderToStaticMarkup(<DotMatrix state="expand" decorative />);
    expect(html).toContain('aria-hidden="true"');
    expect(html).not.toContain('role="img"');
    expect(html).not.toContain("aria-label");
  });

  it("refuses a label on a decorative glyph", () => {
    const html = renderToStaticMarkup(
      // @ts-expect-error a decorative glyph carries no name, so it takes no label
      <DotMatrix state="expand" decorative label="Toggle" />,
    );
    expect(html).not.toContain("Toggle");
  });
});
