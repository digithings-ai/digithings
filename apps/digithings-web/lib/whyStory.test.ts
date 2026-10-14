import { describe, expect, it } from "vitest";

import { APP_PRESETS } from "@/lib/appPresets";
import {
  beatAtLine,
  emailSwapped,
  meetBox,
  morphIndex,
  revealedLayers,
  storyBeats,
  swappedBoxes,
} from "@/lib/whyStory";

const rag = APP_PRESETS[0];

describe("storyBeats", () => {
  it("walks the rented stack and then the morph, for every app", () => {
    for (const preset of APP_PRESETS) {
      const beats = storyBeats(preset);
      expect(beats).toHaveLength(preset.leftSteps.length + preset.morphSteps.length);
      expect(beats[0]?.phase).toBe("theirs");
      expect(beats.at(-1)?.phase).toBe("digi");
    }
  });
});

describe("revealedLayers", () => {
  it("keeps the digi column blank until a morph beat cuts a row", () => {
    expect(revealedLayers(rag, 0)).toEqual([]);
    expect(revealedLayers(rag, rag.leftSteps.length - 1)).toEqual([]);
    expect(revealedLayers(rag, rag.leftSteps.length)).toEqual([]);
    expect(revealedLayers(rag, rag.leftSteps.length + 1)).toEqual(["models"]);
  });

  it("accumulates layers and does not repeat a shared hosting row", () => {
    const finance = APP_PRESETS.find((preset) => preset.id === "finance");
    expect(finance).toBeTruthy();
    if (!finance) return;
    const last = finance.leftSteps.length + finance.morphSteps.length - 1;
    const layers = revealedLayers(finance, last);
    expect(layers.filter((layer) => layer === "hosting")).toHaveLength(1);
    expect(layers).toContain("models");
    expect(layers).toContain("telemetry");
  });
});

describe("swappedBoxes", () => {
  it("flips nothing during the rented walk and the boxes of each morph beat after", () => {
    expect(swappedBoxes(rag, 0)).toEqual([]);
    expect(morphIndex(rag, rag.leftSteps.length)).toBe(0);
    const afterModels = rag.leftSteps.length + 1;
    expect(swappedBoxes(rag, afterModels)).toEqual(expect.arrayContaining(["api", "model"]));
    expect(emailSwapped(rag, afterModels)).toBe(false);
  });

  it("marks the support send box without pricing a layer", () => {
    const support = APP_PRESETS.find((preset) => preset.id === "support");
    expect(support).toBeTruthy();
    if (!support) return;
    const send = support.morphSteps.findIndex((step) => step.email);
    expect(send).toBeGreaterThan(-1);
    const beat = support.leftSteps.length + send;
    expect(emailSwapped(support, beat)).toBe(true);
    expect(revealedLayers(support, beat)).not.toContain("hosting");
  });
});

describe("beatAtLine", () => {
  it("stays on the opener until the next sentence crosses the line", () => {
    expect(beatAtLine([400, 700, 1000], 80)).toBe(0);
    expect(beatAtLine([40, 700, 1000], 80)).toBe(0);
    expect(beatAtLine([40, 70, 1000], 80)).toBe(1);
    expect(beatAtLine([40, 70, 75], 80)).toBe(2);
  });
});

describe("meetBox", () => {
  it("letterboxes a wide drawing inside a square stage", () => {
    const box = meetBox(
      { x: 0, y: 0, width: 100, height: 50 },
      { x: 0, y: 0, width: 200, height: 100 },
      { width: 200, height: 200 },
    );
    expect(box.w).toBeCloseTo(100);
    expect(box.h).toBeCloseTo(50);
    expect(box.y).toBeCloseTo(50);
  });
});
