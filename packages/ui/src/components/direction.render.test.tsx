/**
 * Direction contract (phase 0.2, #4306).
 *
 * The kit defaults to LTR and RTL is always opt-in. `DirectionProvider`
 * renders `dir` on its root (or on <html> with `root`) and publishes the value
 * through `useDirection`, so a region can be mirrored without touching pages.
 * This is the SSR-visible half of the contract; the visual mirroring is proven
 * on the reference `/rtl` route.
 */
import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { DirectionProvider } from "./ThemeProvider";

describe("DirectionProvider", () => {
  it('propagates dir="rtl" to its rendered root', () => {
    const html = renderToStaticMarkup(
      <DirectionProvider dir="rtl">
        <span>mirrored</span>
      </DirectionProvider>,
    );
    expect(html).toContain('dir="rtl"');
    expect(html).toContain("mirrored");
  });

  it("defaults to ltr", () => {
    const html = renderToStaticMarkup(
      <DirectionProvider>
        <span>canonical</span>
      </DirectionProvider>,
    );
    expect(html).toContain('dir="ltr"');
  });

  it("nests: the closest provider wins for its subtree", () => {
    const html = renderToStaticMarkup(
      <DirectionProvider dir="ltr">
        <DirectionProvider dir="rtl">
          <span>inner</span>
        </DirectionProvider>
      </DirectionProvider>,
    );
    expect(html).toContain('dir="ltr"');
    expect(html).toContain('dir="rtl"');
  });
});
