"use client";

import { DIGIQUANT } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";

/** Pixel lockup for the hero: DIGIQUANT drawn from the shared hero-banner
 *  definition (`packages/hero-banner`, `DIGIQUANT`: rise 250 ms + 16 ms per
 *  column, build done 1858 ms, seed 0x9a17). The hero (`replay`) builds on
 *  every load (`replayLoading`); `phase="idle"` holds the mark back until it
 *  flips to `run`. Scroll-triggered marks stay unarmed until allowed.
 *  Reduced motion paints the settled mark with no build (inside `HeroBanner`,
 *  not in CSS). The server render and a no-JS page show the settled mark:
 *  `HeroBanner` renders it as a CSS mask over a themed background, so the
 *  canvas is never an empty box before it paints. `className` stays on the
 *  canvas so the callers' fixed
 *  widths (`top`, footer) size it exactly as before; the `h-`fixed callers
 *  (`_nav`, desk frame) carry explicit pixel widths for the same reason. */
export function quantArmed({ phase, armed }: { phase: "run" | "idle"; armed: boolean }): boolean {
  return armed && phase !== "idle";
}

export function QuantWordmark({
  className,
  phase = "run",
  armed = true,
  replay = false,
}: {
  className?: string;
  phase?: "run" | "idle";
  armed?: boolean;
  replay?: boolean;
}) {
  return (
    <HeroBanner
      def={DIGIQUANT}
      replayLoading={replay}
      armed={quantArmed({ phase, armed })}
      className={className}
    />
  );
}
