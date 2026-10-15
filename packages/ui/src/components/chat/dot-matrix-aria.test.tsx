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
});
