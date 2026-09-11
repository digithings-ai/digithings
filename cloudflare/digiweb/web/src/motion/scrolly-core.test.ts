import { describe, expect, it } from "vitest";
import { progressToIndex, scrollyTrackHeightVh, STEPPER_MEDIA_QUERY } from "./scrolly-core";

describe("progressToIndex", () => {
  it("maps progress into equal per-slide dwells", () => {
    expect(progressToIndex(0, 3)).toBe(0);
    expect(progressToIndex(0.2, 3)).toBe(0);
    expect(progressToIndex(0.34, 3)).toBe(1);
    expect(progressToIndex(0.67, 3)).toBe(2);
  });

  it("maps progress exactly at 1 to the last slide (not out of range)", () => {
    expect(progressToIndex(1, 3)).toBe(2);
    expect(progressToIndex(1, 5)).toBe(4);
  });

  it("clamps out-of-range progress", () => {
    expect(progressToIndex(-0.5, 4)).toBe(0);
    expect(progressToIndex(1.5, 4)).toBe(3);
  });

  it("is safe for degenerate slide counts", () => {
    expect(progressToIndex(0.5, 0)).toBe(0);
    expect(progressToIndex(0.5, 1)).toBe(0);
    expect(progressToIndex(0.9, -2)).toBe(0);
  });
});

describe("scrollyTrackHeightVh", () => {
  it("derives the budget from slide count (content), not a fixed multiple", () => {
    expect(scrollyTrackHeightVh(3)).toBe(270);
    expect(scrollyTrackHeightVh(5)).toBe(450);
  });

  it("honors a custom per-slide dwell", () => {
    expect(scrollyTrackHeightVh(4, 120)).toBe(480);
  });

  it("floors at one slide of budget", () => {
    expect(scrollyTrackHeightVh(0)).toBe(90);
    expect(scrollyTrackHeightVh(-3, 100)).toBe(100);
  });
});

describe("STEPPER_MEDIA_QUERY", () => {
  it("triggers the flow fallback on small viewports and reduced-motion", () => {
    expect(STEPPER_MEDIA_QUERY).toContain("max-width");
    expect(STEPPER_MEDIA_QUERY).toContain("prefers-reduced-motion: reduce");
  });
});
