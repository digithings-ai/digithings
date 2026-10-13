/**
 * DIG-2864 acceptance: every banner renders and animates in OpenTUI at 120x30
 * and 80x24, from the same definitions the web renderer reads.
 */
import { testRender } from "@opentui/react/test-utils";
import { afterEach, describe, expect, test } from "bun:test";

import { streamPass, type ScrambleState } from "../../../packages/hero-banner/src/animations/scramble";
import { BANNERS } from "../../../packages/hero-banner/src/definitions";
import { preparedBanner } from "../../../packages/hero-banner/src/engine";
import type { BannerDefinition } from "../../../packages/hero-banner/src/types";
import { HeroBanner } from "./hero-banner";

let current: Awaited<ReturnType<typeof testRender>> | null = null;

afterEach(() => {
  current?.renderer.destroy();
  current = null;
});

async function frameAt(
  def: BannerDefinition,
  size: { width: number; height: number },
  holdMs: number,
  env: Record<string, string | undefined> = {},
): Promise<string> {
  current?.renderer.destroy();
  current = await testRender(
    <HeroBanner def={def} cols={size.width} rows={size.height} holdMs={holdMs} env={env} />,
    size,
  );
  await current.renderOnce();
  return current.captureCharFrame();
}

/** The frame as a viewer sees it: characters plus colours. A door that only
 *  changes colour (DIGIVAULT's dial clicks) still moves. */
async function lookAt(
  def: BannerDefinition,
  size: { width: number; height: number },
  holdMs: number,
): Promise<string> {
  const chars = await frameAt(def, size, holdMs);
  const colours = current!
    .captureSpans()
    .lines.map((line) => line.spans.map((span) => `${span.width}:${JSON.stringify(span.fg)}/${JSON.stringify(span.bg)}`).join(" "))
    .join("\n");
  return `${chars}\n${colours}`;
}

const mark = (frame: string) => frame.split("\n").filter((line) => /[█▀▄]/.test(line));

for (const def of Object.values(BANNERS)) {
  describe(`${def.id} in OpenTUI`, () => {
    for (const size of [{ width: 120, height: 30 }, { width: 80, height: 24 }]) {
      test(`${size.width}x${size.height}: renders five rows inside the terminal, and animates`, async () => {
        const loadingMs = def.animation.loadingMs(preparedBanner(def).state);
        const settled = await frameAt(def, size, 0, { NO_MOTION: "1" });
        const rows = mark(settled);
        expect(rows.length).toBe(5);
        for (const line of settled.split("\n")) expect(line.length).toBeLessThanOrEqual(size.width);

        // LOADING moves: early intro frames differ from each other and from the settled
        // mark (digichat locks its letters well before its LOADING window closes).
        const early = await lookAt(def, size, Math.round(loadingMs * 0.15));
        const mid = await lookAt(def, size, Math.round(loadingMs * 0.35));
        expect(early).not.toBe(mid);
        expect(await frameAt(def, size, Math.round(loadingMs * 0.35))).not.toBe(settled);

        // Reduced motion never moves.
        expect(await frameAt(def, size, Math.round(loadingMs * 0.35), { NO_MOTION: "1" })).toBe(settled);
      });
    }
  });
}

test("LIVE keeps moving after LOADING; HERO_BANNER_LIVE=0 settles", async () => {
  const size = { width: 120, height: 30 };
  const def = BANNERS.digivoice;
  const a = await frameAt(def, size, 3000);
  const b = await frameAt(def, size, 3300);
  expect(a).not.toBe(b);
  const offA = await frameAt(def, size, 3000, { HERO_BANNER_LIVE: "0" });
  const offB = await frameAt(def, size, 3300, { HERO_BANNER_LIVE: "0" });
  expect(offA).toBe(offB);
});

/**
 * DIG-2695: `DIGI_REDUCED_MOTION` is the flag motion.ts documents as drawing
 * EVERY animation at its settled frame. The banner is one of those animations
 * and used to ignore it, so an operator who set the flag still got a moving
 * wordmark. Same spelling as NO_MOTION, same outcome.
 */
test("DIGI_REDUCED_MOTION settles the banner exactly like NO_MOTION", async () => {
  const size = { width: 120, height: 30 };
  const def = BANNERS.digichat;
  const loadingMs = def.animation.loadingMs(preparedBanner(def).state);
  const mid = Math.round(loadingMs * 0.35);

  const settled = await frameAt(def, size, 0, { NO_MOTION: "1" });

  // Non-vacuity: with no flag the banner really does move, so "settled" is a
  // distinct frame and the equality below cannot be met by two moving frames.
  expect(await frameAt(def, size, mid)).not.toBe(settled);

  // The flag under test, at the same instant, must land on the settled frame.
  expect(await frameAt(def, size, mid, { DIGI_REDUCED_MOTION: "1" })).toBe(settled);

  // And it must stay there, not merely land there.
  expect(await frameAt(def, size, Math.round(loadingMs * 0.8), { DIGI_REDUCED_MOTION: "1" })).toBe(settled);
});

/** The frame with colours: the digichat stream changes tones, not glyph shapes. */
async function colorsAt(
  def: BannerDefinition,
  size: { width: number; height: number },
  holdMs: number,
  env: Record<string, string | undefined> = {},
): Promise<string> {
  await frameAt(def, size, holdMs, env);
  return current!
    .captureSpans()
    .lines.map((line) => line.spans.map((s) => `${s.text}@${[s.fg.r, s.fg.g, s.fg.b].join(",")}`).join("|"))
    .join("\n");
}

describe("digichat LIVE streams tokens in OpenTUI (DIG-2865)", () => {
  const def = BANNERS.digichat;
  const state = preparedBanner(def).state as ScrambleState;
  const live = state.options.live;
  const loadingMs = def.animation.loadingMs(state);
  const quietMs = live?.kind === "stream" ? live.quietMs : 0;
  const landAt = streamPass(state, 0);
  const passAt = loadingMs + quietMs + landAt[Math.floor(landAt.length / 2)]! + 10;

  for (const size of [{ width: 120, height: 30 }, { width: 80, height: 24 }]) {
    test(`${size.width}x${size.height}: quiet, then a token pass, then settled; off and reduced stay still`, async () => {
      expect(live?.kind).toBe("stream");
      const settledChars = await frameAt(def, size, 0, { NO_MOTION: "1" });
      const settled = await colorsAt(def, size, 0, { NO_MOTION: "1" });
      expect(await colorsAt(def, size, loadingMs + quietMs / 2)).toBe(settled);
      // Mid-pass: same letters, different tones (dim ghost ahead, flash at the head).
      expect(await frameAt(def, size, passAt)).toBe(settledChars);
      expect(await colorsAt(def, size, passAt)).not.toBe(settled);
      expect(await colorsAt(def, size, loadingMs + state.streamPeriodMs - 1)).toBe(settled);
      expect(await colorsAt(def, size, passAt, { HERO_BANNER_LIVE: "0" })).toBe(settled);
      expect(await colorsAt(def, size, passAt, { NO_MOTION: "1" })).toBe(settled);
    });
  }
});
