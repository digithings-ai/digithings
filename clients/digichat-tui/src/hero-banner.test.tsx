/**
 * DIG-2864 acceptance: every banner renders and animates in OpenTUI at 120x30
 * and 80x24, from the same definitions the web renderer reads.
 */
import { testRender } from "@opentui/react/test-utils";
import { afterEach, describe, expect, test } from "bun:test";

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
        // Sampled at several points: an animation can hold one glyph frame across a
        // phase (digivault's dial reads the same at 15% and 35% at half-block size).
        const frames: string[] = [];
        for (const at of [0.15, 0.35, 0.55, 0.75]) frames.push(await frameAt(def, size, Math.round(loadingMs * at)));
        expect(new Set(frames).size).toBeGreaterThan(1);
        expect(frames.some((frame) => frame !== settled)).toBe(true);

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
