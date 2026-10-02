import { describe, expect, it } from "vitest";
import { DECK_GAP, DECK_MOTION_QUERY, DECK_THREE_MIN, DECK_TWO_MIN, deckPhaseCount, deckPose, deckVisibleCount } from "./deck-motion";

const CARD = 280;

describe("deckVisibleCount", () => {
  it("shows one card on a phone, two on a narrower desktop, three when wide", () => {
    expect(deckVisibleCount(390)).toBe(1);
    expect(deckVisibleCount(DECK_TWO_MIN - 1)).toBe(1);
    expect(deckVisibleCount(DECK_TWO_MIN)).toBe(2);
    expect(deckVisibleCount(1280)).toBe(2);
    expect(deckVisibleCount(DECK_THREE_MIN - 1)).toBe(2);
    expect(deckVisibleCount(DECK_THREE_MIN)).toBe(3);
    expect(deckVisibleCount(1800)).toBe(3);
  });
});

describe("deck motion", () => {
  it("only animates when reduced motion is not requested", () => {
    expect(DECK_MOTION_QUERY).toContain("prefers-reduced-motion: no-preference");
    expect(DECK_MOTION_QUERY).toContain(`min-width: ${DECK_TWO_MIN}px`);
  });

  it("starts as a stack, then the visible cards sit in separate slots", () => {
    const visible = 3;
    const phases = deckPhaseCount(7, visible);
    const stride = CARD + DECK_GAP;
    const stacked = [0, 1, 2].map((i) => deckPose(i, 7, visible, 0, CARD, DECK_GAP));
    expect(stacked[0]?.x).toBe(0);
    expect(stacked[1]?.x).toBe(0);
    expect(stacked[2]?.x).toBe(0);
    expect(stacked[1]?.y).toBeGreaterThan(stacked[0]?.y ?? 0);
    expect(stacked[0]?.z).toBeGreaterThan(stacked[1]?.z ?? 0);

    const spread = [0, 1, 2].map((i) => deckPose(i, 7, visible, 1 / phases, CARD, DECK_GAP));
    expect(spread[0]?.x).toBe(0);
    expect(spread[1]?.x).toBe(stride);
    expect(spread[2]?.x).toBe(2 * stride);
  });

  it("stacks the next card onto the right, then slides the row under it", () => {
    const visible = 2;
    const phases = deckPhaseCount(7, visible);
    const stride = CARD + DECK_GAP;
    const midStack = (1 + 0.2) / phases;
    const before = deckPose(2, 7, visible, 1 / phases, CARD, DECK_GAP);
    const stacking = deckPose(2, 7, visible, midStack, CARD, DECK_GAP);
    const seated = deckPose(0, 7, visible, midStack, CARD, DECK_GAP);
    expect(stacking.x).toBeLessThan(before.x);
    expect(stacking.x).toBeGreaterThan((visible - 1) * stride);
    expect(seated.x).toBe(0);

    const midSlide = (1 + 0.7) / phases;
    const sliding = deckPose(0, 7, visible, midSlide, CARD, DECK_GAP);
    const incoming = deckPose(2, 7, visible, midSlide, CARD, DECK_GAP);
    expect(sliding.x).toBeLessThan(0);
    expect(incoming.x).toBe((visible - 1) * stride);
  });

  it("ends on the last two or three cards, in order", () => {
    const stride = CARD + DECK_GAP;
    const wide = [4, 5, 6].map((i) => deckPose(i, 7, 3, 1, CARD, DECK_GAP));
    expect(wide.map((pose) => pose.x)).toEqual([0, stride, 2 * stride]);
    expect(deckPose(0, 7, 3, 1, CARD, DECK_GAP).opacity).toBe(0);

    const narrow = [5, 6].map((i) => deckPose(i, 7, 2, 1, CARD, DECK_GAP));
    expect(narrow.map((pose) => pose.x)).toEqual([0, stride]);
    expect(deckPose(0, 7, 2, 1, CARD, DECK_GAP).opacity).toBe(0);
  });
});
