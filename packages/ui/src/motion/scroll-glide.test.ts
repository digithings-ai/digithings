import { describe, expect, it } from "vitest";

import {
  REST_COMMIT_GLIDE,
  REST_GLIDE_MS,
  REST_QUIET_MS,
  applyRestBlend,
  restBlendAmount,
  shouldStartRestGlide,
} from "./scroll-glide";

describe("shouldStartRestGlide", () => {
  it("stays with the page while the reader is still moving", () => {
    expect(shouldStartRestGlide({ quietMs: REST_QUIET_MS - 1, liveGlide: 0.3 })).toBe(false);
  });

  it("eases back onto the narrated boxes once the page has rested", () => {
    expect(shouldStartRestGlide({ quietMs: REST_QUIET_MS, liveGlide: 0.3 })).toBe(true);
  });

  it("does nothing when the camera is already parked", () => {
    expect(shouldStartRestGlide({ quietMs: 400, liveGlide: 0 })).toBe(false);
    expect(shouldStartRestGlide({ quietMs: 400, liveGlide: 0.02 })).toBe(false);
  });

  it("does not rewind a skip that has already committed to the next beat", () => {
    expect(shouldStartRestGlide({ quietMs: 400, liveGlide: REST_COMMIT_GLIDE })).toBe(false);
    expect(shouldStartRestGlide({ quietMs: 400, liveGlide: 0.9 })).toBe(false);
  });
});

describe("restBlendAmount", () => {
  it("smoothsteps across the glide and clamps the ends", () => {
    expect(restBlendAmount(0, REST_GLIDE_MS)).toBe(0);
    expect(restBlendAmount(REST_GLIDE_MS, REST_GLIDE_MS)).toBe(1);
    expect(restBlendAmount(REST_GLIDE_MS / 2, REST_GLIDE_MS)).toBeCloseTo(0.5, 5);
    expect(restBlendAmount(-20, REST_GLIDE_MS)).toBe(0);
    expect(restBlendAmount(REST_GLIDE_MS + 40, REST_GLIDE_MS)).toBe(1);
  });
});

describe("applyRestBlend", () => {
  it("shows the scroll pose while skipping and the parked pose at rest", () => {
    expect(applyRestBlend(0.4, 0)).toBeCloseTo(0.4, 5);
    expect(applyRestBlend(0.4, 1)).toBe(0);
    expect(applyRestBlend(0.4, 0.5)).toBeCloseTo(0.2, 5);
  });

  it("clamps a blend that runs past the glide", () => {
    expect(applyRestBlend(1.4, -0.2)).toBe(1);
    expect(applyRestBlend(0.4, 2)).toBe(0);
  });
});
