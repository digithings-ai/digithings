import { describe, expect, it } from "vitest";
import { renderToStaticMarkup } from "react-dom/server";
import { PipelineBand } from "@/app/_bands/pipeline";
import { STAGE_COPY } from "./stage-copy";

describe("PipelineBand", () => {
  const html = renderToStaticMarkup(<PipelineBand />);

  it("states the capture reason and does not invent a run", () => {
    expect(html).toContain("no recorded run");
    expect(html).toContain("Reading the latest run from the official API.");
    expect(html).toContain("dashboard-api GET /v1/tables/documents");
    expect(html).toContain("No run detail was recorded in this build.");
    expect(html).toContain("—");
    expect(html).not.toContain("sample run A");
    expect(html).not.toContain("sample timeline");
    expect(html).not.toContain("99.909");
    expect(html).not.toContain("204.04");
    expect(html).not.toContain("legacy_estimate");
  });

  it("keeps the six stage names and the unwired execution card", () => {
    expect(html).toContain("Inputs");
    expect(html).toContain("Learning");
    expect(html).toContain("in development");
    expect(html).toContain("nothing places an order");
  });

  it("gives every stage its full copy and a button for each sub-step", () => {
    for (const copy of Object.values(STAGE_COPY)) {
      expect(html).toContain(copy.does);
      for (const step of copy.steps) {
        expect(html).toContain(step);
        expect(html).toMatch(new RegExp(`<button[^>]*>[\\s\\S]*${step.replace(/[.*+?^${}()|[\]\\]/g, "\\$&")}[\\s\\S]*</button>`));
      }
    }
    expect(html).toContain('aria-expanded="false"');
    expect(html).not.toContain("truncate");
    expect(html).not.toContain("line-clamp");
  });

  it("lays the deck out as one, two, then three cards and does not scroll a cramped strip", () => {
    expect(html).toContain("grid-cols-1");
    expect(html).toContain("lg:grid-cols-2");
    expect(html).toContain("min-[1440px]:grid-cols-3");
    expect(html).toContain("min-h-[28rem]");
    expect(html).toContain("motion-safe:");
    expect(html).not.toContain("overflow-x-auto");
    expect(html).not.toContain("snap-x");
    expect(html).not.toContain("snap-start");
  });
});
