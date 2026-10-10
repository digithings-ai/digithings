import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

describe("hero canvas scale", () => {
  it("paints candles and volume from the digiquant chart scale", () => {
    const src = readFileSync(new URL("../app/_chrome/QuantField.tsx", import.meta.url), "utf8");
    expect(src).toContain('from "@digithings/ui/chart-scale"');
    expect(src).toContain("readDigiquantChartScale");
    expect(src).toContain("scale.candleUp");
    expect(src).toContain("scale.candleDown");
    expect(src).toContain("scale.volumeUp");
    expect(src).toContain("scale.volumeDown");
    expect(src).toContain("scale.sma");
    expect(src).toContain("scale.ema");
    expect(src).toContain("heroOverlayInputs(overlayKind, scale)");
    expect(src).not.toContain("#3DFF9A");
    expect(src).not.toContain("#FF5C6C");
  });
});
