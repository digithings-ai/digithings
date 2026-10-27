import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { BrandWordmark } from "./BrandWordmark";

describe("BrandWordmark", () => {
  it("names the brand and paints the shared mask", () => {
    const html = renderToStaticMarkup(<BrandWordmark />);
    expect(html).toContain('aria-label="digithings"');
    expect(html).toContain("brand-wordmark");
    expect(html).toContain("url(&quot;/wordmark-mask.svg&quot;)");
  });

  it("accepts a base-path mask", () => {
    const html = renderToStaticMarkup(<BrandWordmark mask="/chat/wordmark-mask.svg" />);
    expect(html).toContain("/chat/wordmark-mask.svg");
  });
});
