"use client";

import { DIGIQUANT } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";

/** Pixel lockup for the hero: DIGIQUANT drawn from the shared hero-banner
 *  definition (`packages/hero-banner`, `DIGIQUANT`: rise 250 ms + 16 ms per
 *  column, build done 1858 ms, seed 0x9a17). The hero (`replay`) builds on
 *  every load (`replayLoading`); `phase="idle"` holds the mark back until it
 *  flips to `run` (mapped to `armed`); scroll-triggered marks stay unarmed
 *  until allowed. Reduced motion paints the settled mark with no build
 *  (inside `HeroBanner`, not in CSS). */
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
  const idle = phase === "idle";
  return (
    <HeroBanner
      def={DIGIQUANT}
      replayLoading={replay}
      armed={armed && !idle}
      className={className}
    />
  );
}
