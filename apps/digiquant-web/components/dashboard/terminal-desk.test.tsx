import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DashboardBand } from "@/app/_bands/dashboard";

describe("DashboardBand", () => {
  const html = renderToStaticMarkup(<DashboardBand />);

  it("composes the portfolio windows and withholds figures", () => {
    expect(html).toContain("01 / Book");
    expect(html).toContain("04 / Holdings");
    expect(html).toContain("06 / Drawdown");
    expect(html).toContain("12×12");
    expect(html).toContain("Reading the official API.");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).toContain("—");
    expect(html).not.toContain("recording to come");
    expect(html).not.toContain("Dashboard · product view");
    expect(html).not.toContain("sample run");
  });
});
