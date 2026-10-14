import { describe, expect, it } from "vitest";

import {
  CAM_IDENTITY,
  camTransform,
  fitCamera,
  glideAmount,
  lerpCam,
  mixSpot,
  unionSpot,
  walkCursor,
} from "./tour-camera";

describe("walkCursor", () => {
  it("gives each step an equal slice and keeps progress 1 on the last step", () => {
    expect(walkCursor(0, 11)).toEqual({ index: 0, frac: 0 });
    expect(walkCursor(1, 11)).toEqual({ index: 10, frac: 1 });
    expect(walkCursor(0.5, 2)).toEqual({ index: 1, frac: 0 });
  });

  it("parks a gesture in the middle of a step", () => {
    const cursor = walkCursor(0.5 / 11, 11);
    expect(cursor.index).toBe(0);
    expect(cursor.frac).toBeCloseTo(0.5, 5);
  });

  it("is safe for an empty walk", () => {
    expect(walkCursor(0.4, 0)).toEqual({ index: 0, frac: 0 });
  });
});

describe("glideAmount", () => {
  it("rests through the parked midpoint, then eases to the next boxes", () => {
    expect(glideAmount(0)).toBe(0);
    expect(glideAmount(0.5)).toBe(0);
    expect(glideAmount(0.55)).toBe(0);
    expect(glideAmount(1)).toBe(1);
    expect(glideAmount(0.775)).toBeCloseTo(0.5, 5);
  });
});

describe("lerpCam", () => {
  it("blends scale and pan", () => {
    expect(lerpCam({ k: 1, x: 0, y: 0 }, { k: 1.4, x: -20, y: 10 }, 0.5)).toEqual({
      k: 1.2,
      x: -10,
      y: 5,
    });
  });
});

describe("fitCamera", () => {
  it("stays put when the lit boxes already fill the stage", () => {
    const frame = fitCamera({
      boxes: [{ x: 0, y: 0, w: 700, h: 400 }],
      stageW: 734,
      stageH: 420,
      contentW: 734,
      contentH: 420,
    });
    expect(frame).toEqual(CAM_IDENTITY);
  });

  it("zooms in on a small target and keeps the scale capped", () => {
    const frame = fitCamera({
      boxes: [{ x: 300, y: 40, w: 80, h: 36 }],
      stageW: 734,
      stageH: 420,
      contentW: 734,
      contentH: 420,
    });
    expect(frame.k).toBeGreaterThan(1.02);
    expect(frame.k).toBeLessThanOrEqual(1.45);
    expect(camTransform(frame)).toContain("scale(");
  });

  it("stays put when a cover zoom would only enlarge the whole drawing", () => {
    const frame = fitCamera({
      boxes: [{ x: 10, y: 20, w: 700, h: 300 }],
      stageW: 734,
      stageH: 420,
      contentW: 734,
      contentH: 420,
      cover: true,
      fill: 0.55,
      maxScale: 1.65,
    });
    expect(frame).toEqual(CAM_IDENTITY);
  });

  it("covers a wide short row so the camera travels to it", () => {
    const frame = fitCamera({
      boxes: [{ x: 20, y: 300, w: 560, h: 40 }],
      stageW: 734,
      stageH: 420,
      contentW: 734,
      contentH: 420,
      cover: true,
      fill: 0.55,
      maxScale: 1.65,
    });
    expect(frame.k).toBeGreaterThan(1.02);
    expect(frame.k).toBeLessThanOrEqual(1.65);
    expect(frame.y).not.toBe(0);
  });

  it("never zooms a cover target past the stage less its margin", () => {
    const frame = fitCamera({
      boxes: [{ x: 20, y: 0, w: 600, h: 40 }],
      stageW: 734,
      stageH: 420,
      contentW: 734,
      contentH: 420,
      cover: true,
      fill: 0.9,
      maxScale: 3,
    });
    expect(frame.k * 600).toBeLessThanOrEqual(734 - 2 * 24 + 0.01);
  });

  it("keeps every lit box on screen with the margin clear", () => {
    const stageW = 803;
    const stageH = 512;
    const pad = 24;
    const cases = [
      { x: 10, y: 20, w: 730, h: 50 },
      { x: 500, y: 380, w: 200, h: 70 },
      { x: 0, y: 440, w: 260, h: 72 },
      { x: 300, y: 0, w: 80, h: 36 },
    ];
    for (const box of cases) {
      const frame = fitCamera({
        boxes: [box],
        stageW,
        stageH,
        contentW: stageW,
        contentH: stageH,
        cover: true,
        fill: 0.55,
        maxScale: 1.65,
        pad,
      });
      const left = (box.x + frame.x) * frame.k;
      const top = (box.y + frame.y) * frame.k;
      const right = left + box.w * frame.k;
      const bottom = top + box.h * frame.k;
      expect(left).toBeGreaterThanOrEqual(0);
      expect(top).toBeGreaterThanOrEqual(0);
      expect(right).toBeLessThanOrEqual(stageW + 0.01);
      expect(bottom).toBeLessThanOrEqual(stageH + 0.01);
      if (frame.k > 1) expect(right - left).toBeLessThanOrEqual(stageW - 2 * pad + 0.01);
    }
  });

  it("respects a tighter scale cap", () => {
    const frame = fitCamera({
      boxes: [{ x: 300, y: 40, w: 80, h: 36 }],
      stageW: 734,
      stageH: 420,
      contentW: 734,
      contentH: 420,
      fill: 0.5,
      maxScale: 1.2,
    });
    expect(frame.k).toBe(1.2);
  });
});

describe("unionSpot", () => {
  it("drops the spotlight when the union is the whole drawing", () => {
    expect(unionSpot([{ x: 0, y: 0, w: 700, h: 400 }], 734, 420)).toBeNull();
  });

  it("frames a focused box", () => {
    const spot = unionSpot([{ x: 40, y: 20, w: 80, h: 36 }], 734, 420);
    expect(spot).toMatchObject({ left: 34, top: 14, width: 92, height: 48 });
  });
});

describe("mixSpot", () => {
  it("fades a spotlight in and out at the whole-graph beats", () => {
    const focused = { left: 10, top: 10, width: 40, height: 20 };
    expect(mixSpot(null, focused, 0)?.opacity).toBe(0);
    expect(mixSpot(null, focused, 1)?.opacity).toBe(1);
    expect(mixSpot(focused, null, 1)?.opacity).toBe(0);
    expect(mixSpot(null, null, 0.5)).toBeNull();
  });
});
