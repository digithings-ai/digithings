import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { DashboardBand } from "@/app/_bands/dashboard";

describe("DashboardBand", () => {
  const html = renderToStaticMarkup(<DashboardBand />);

  it("uses the empty walkthrough frame until a recording is published", () => {
    expect(html).toContain("recording to come");
    expect(html).toContain("Placeholder · no recording yet");
    expect(html).toContain("No walkthrough is published in this build");
    expect(html).not.toContain("Dashboard · product view");
    expect(html).not.toContain("sample run");
  });

  it("keeps the product ledger and the dashboard path", () => {
    expect(html).toContain("strategy builder");
    expect(html).toContain('href="/dashboard/"');
    expect(html).toContain("Open the dashboard");
  });
});
