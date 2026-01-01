"use client";

import { DIGITHINGS } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";

/** @deprecated Pages use `BrandWordmark` (the studio 4×4 mask). This still
 *  draws the hero-banner `DIGITHINGS` cells for anything that has not moved.
 *  Do not mount it on the digithings hero, nav, or footer.
 *
 *  Pixel lockup, drawn from the shared hero-banner definition
 *  (`packages/hero-banner`, `DIGITHINGS`: build 1400 ms, tick 40 ms).
 *  The hero builds on every load (`replayLoading`); the footer is the same
 *  mark at page width and stays blank until `live` flips the first time it
 *  scrolls into view. Reduced motion paints the settled mark with no build
 *  (inside `HeroBanner`, not in CSS). The `.pixel-word` wrapper keeps the
 *  responsive widths and the band aspect the footer ruling pins. */
export function PixelWordmark({
  variant = "hero",
  live = false,
}: {
  variant?: "hero" | "footer";
  live?: boolean;
}) {
  if (variant === "footer") {
    return (
      <div className="pixel-word pixel-word-footer">
        <HeroBanner def={DIGITHINGS} live={live} armed={live} />
      </div>
    );
  }
  return (
    <div className="pixel-word pixel-word-hero is-live">
      <HeroBanner def={DIGITHINGS} replayLoading />
    </div>
  );
}
