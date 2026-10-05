import { renderToStaticMarkup } from "react-dom/server";
import { describe, expect, it } from "vitest";

import { PricingMatrix } from "./PricingMatrix";

describe("PricingMatrix narrow layout", () => {
  const html = renderToStaticMarkup(
    <PricingMatrix
      tiers={[
        { name: "self-host", price: "$0" },
        { name: "service", price: "on contact", popular: true },
      ]}
      groups={[
        {
          label: "price",
          rows: [{ label: "what you pay", cells: ["$0 — no account", "scoped"] }],
        },
      ]}
    />,
  );

  it("stacks each tier for narrow screens and keeps the comparison table", () => {
    expect(html).toContain("md:hidden");
    expect(html).toContain("hidden overflow-x-auto md:block");
    expect(html).toContain("<h3");
    expect(html).toContain("self-host");
    expect(html).toContain("what you pay");
    expect(html).toContain("$0 — no account");
  });
});
