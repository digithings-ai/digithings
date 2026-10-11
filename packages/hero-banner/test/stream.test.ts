/**
 * DIG-2865: digichat LIVE is a streaming-token pass on the SCRAMBLE recipe.
 */
import { describe, expect, test } from "bun:test";

import { streamPass, type ScrambleState } from "../src/animations/scramble";
import { DIGICHAT } from "../src/definitions";
import { preparedBanner, sampleBanner } from "../src/engine";
import type { Frame } from "../src/types";

const state = preparedBanner(DIGICHAT).state as ScrambleState;
const live = state.options.live;
if (live?.kind !== "stream") throw new Error("DIGICHAT LIVE must be stream");
const loadingMs = DIGICHAT.animation.loadingMs(state);
const still = DIGICHAT.animation.still(state);

const tones = (frame: Frame) => new Set(frame.pixels.filter((p) => p).map((p) => p!.tone));
const lit = (frame: Frame) => frame.pixels.map((p) => p != null);
/** A LIVE frame `p` ms into stream pass `pass`. */
const inPass = (pass: number, p: number) =>
  sampleBanner(DIGICHAT, { t: loadingMs + pass * state.streamPeriodMs + live.quietMs + p }).frame;

describe("streamPass", () => {
  test("deterministic, left to right, tokens of 1-3 letters at the set latencies", () => {
    for (let pass = 0; pass < 50; pass += 1) {
      const landAt = streamPass(state, pass);
      expect(streamPass(state, pass)).toEqual(landAt);
      expect(landAt.length).toBe(DIGICHAT.text.length);
      expect(landAt[0]).toBe(live.tokenMs[0]);
      let run = 1;
      for (let i = 1; i < landAt.length; i += 1) {
        const step = landAt[i]! - landAt[i - 1]!;
        if (step === 0) {
          run += 1;
          expect(run).toBeLessThanOrEqual(live.maxToken);
        } else {
          run = 1;
          expect(step).toBeGreaterThanOrEqual(live.tokenMs[0]);
          expect(step).toBeLessThanOrEqual(live.tokenMs[1]);
        }
      }
      // The pass ends (last flash done) inside its slot.
      expect(landAt.at(-1)! + state.options.flashMs).toBeLessThanOrEqual(state.streamPeriodMs - live.quietMs);
    }
  });

  test("the token split changes between passes", () => {
    const splits = new Set(Array.from({ length: 8 }, (_, pass) => streamPass(state, pass).join(",")));
    expect(splits.size).toBeGreaterThan(4);
  });
});

describe("digichat LIVE", () => {
  test("rests on the settled mark through the quiet stretch", () => {
    for (let t = 0; t < live.quietMs; t += 200) {
      expect(sampleBanner(DIGICHAT, { t: loadingMs + t }).frame).toEqual(still);
    }
  });

  test("a pass drops to the dim ghost, streams back with flashes, and settles", () => {
    expect(tones(inPass(0, 0))).toEqual(new Set(["dim"]));
    const mid = streamPass(state, 0);
    const midT = mid[Math.floor(mid.length / 2)]! + 10;
    expect(tones(inPass(0, midT))).toContain("flash");
    expect(tones(inPass(0, midT))).toContain("dim");
    const end = state.streamPeriodMs - live.quietMs - 1;
    expect(inPass(0, end)).toEqual(still);
  });

  test("every letter is always the right glyph", () => {
    for (let p = 0; p < state.streamPeriodMs - live.quietMs; p += 40) {
      expect(lit(inPass(1, p))).toEqual(lit(still));
    }
  });

  test("reduced motion and LIVE off stay on the settled mark", () => {
    for (let p = 0; p < 1500; p += 40) {
      const t = loadingMs + live.quietMs + p;
      expect(sampleBanner(DIGICHAT, { t, motion: "reduced" }).frame).toEqual(still);
      expect(sampleBanner(DIGICHAT, { t, live: false }).frame).toEqual(still);
    }
  });

  test("skipLoading starts in LIVE at mount", () => {
    expect(sampleBanner(DIGICHAT, { t: live.quietMs, skipLoading: true }).phase).toBe("live");
    expect(tones(sampleBanner(DIGICHAT, { t: live.quietMs, skipLoading: true }).frame)).toEqual(new Set(["dim"]));
  });
});
