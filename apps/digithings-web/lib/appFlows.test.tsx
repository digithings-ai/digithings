import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";

import { AppFirstSection } from "@/components/landing/AppFirstSection";
import { APP_FLOWS } from "@/lib/appFlows";

describe("app flows", () => {
  it("draws the three digithings apps and not someone else's agents", () => {
    expect(Object.keys(APP_FLOWS)).toEqual(["rag", "support", "finance"]);
    const html = renderToStaticMarkup(<AppFirstSection />);
    expect(html).toContain("digichat");
    expect(html).toContain("digigraph");
    expect(html).toContain("digisearch");
    expect(html).toContain("digillm");
    expect(html).toContain("ask again until the answer is enough");
    expect(html).not.toMatch(/Grokopedia|Claude|Jev|Opus|Fable|advisor/);
    expect(html).not.toMatch(/DigiChat|DigiGraph|DigiQuant/);
  });
});
