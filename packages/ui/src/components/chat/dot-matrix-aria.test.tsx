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

  it("clips the name in place so it does not paint beside the label", () => {
    const html = renderToStaticMarkup(<DotMatrix state="success" label="Worked" />);
    expect(html).toContain('data-slot="screen-reader-name"');
    expect(html).toContain(">Worked<");
    expect(html).toContain("position:absolute");
    expect(html).toContain("width:1px");
    expect(html).toContain("height:1px");
    expect(html).toContain("overflow:hidden");
    expect(html).toContain("clip-path:inset(50%)");
    expect(html).not.toMatch(/left\s*:/);
    expect(html).not.toContain("sr-only");
  });
});
