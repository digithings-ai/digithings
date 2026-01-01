import { expect, test } from "bun:test";

import { heroWordmarkLines, SETTLED_MS, wordmarkLines } from "../../../packages/ui/src/components/chat/digichat-wordmark";
import motion from "../../../packages/design/motion.json";
import { FRAME, reducedMotion } from "./motion";

test("frame clocks come from the shared motion tokens", () => {
  expect(FRAME).toEqual(motion.frame);
  expect(FRAME.spinner).toBe(80);
  expect(FRAME.caret).toBe(530);
});

test("DIGI_REDUCED_MOTION and NO_MOTION switch motion off", () => {
  expect(reducedMotion({})).toBe(false);
  expect(reducedMotion({ DIGI_REDUCED_MOTION: "1" })).toBe(true);
  expect(reducedMotion({ NO_MOTION: "1" })).toBe(true);
  expect(reducedMotion({ DIGI_REDUCED_MOTION: "0" })).toBe(false);
  expect(reducedMotion({ NO_MOTION: "" })).toBe(false);
  expect(reducedMotion({ NO_MOTION: "false" })).toBe(false);
});

test("the reduced-motion wordmark is the settled word, with no flash", () => {
  const still = wordmarkLines("DIGICHAT", { cols: 100, tMs: SETTLED_MS });
  const settled = heroWordmarkLines("DIGICHAT", { cols: 100, elapsed: 0, full: false });
  expect(still.lines).toEqual(settled.lines);
});
