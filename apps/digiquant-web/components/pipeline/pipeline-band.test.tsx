import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PipelineBand } from "@/app/_bands/pipeline";

describe("PipelineBand", () => {
  const html = renderToStaticMarkup(<PipelineBand />);

  it("states that this build has no recorded run and does not invent one", () => {
    expect(html).toContain("no recorded run");
    expect(html).toContain("No run source reachable");
    expect(html).not.toContain("sample run A");
    expect(html).not.toContain("sample timeline");
  });

  it("keeps the six stage names and the unwired execution card", () => {
    expect(html).toContain("Inputs");
    expect(html).toContain("Learning");
    expect(html).toContain("in development");
    expect(html).toContain("nothing places an order");
  });
});
