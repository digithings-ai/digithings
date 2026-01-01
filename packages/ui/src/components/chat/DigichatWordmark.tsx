"use client";

import { DIGICHAT } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";

/** Square-pixel DIGICHAT mark, drawn from the shared hero-banner definition
 *  (`packages/hero-banner`, `DIGICHAT`: scramble 80/240/180 with a 960 hold,
 *  settled at 2000 ms, seed 0). Plays once per tab — the session claim lives
 *  inside `HeroBanner`, so header remounts keep the settled mark instead of
 *  replaying. `live={false}` keeps the replaced component's settled behavior
 *  rather than the definition's streaming LIVE pass. Reduced motion paints
 *  the settled mark with no scramble (inside `HeroBanner`, not in CSS). The
 *  fixed 140x20 box preserves the replaced SVG's intrinsic size (70x10 units
 *  at cell 2); the `span` keeps both callers' `<span>` nesting valid. The
 *  server render and a no-JS page show the settled mark: `HeroBanner`
 *  renders it as a CSS mask over the mark's colour, so the canvas is never an
 *  empty box before it paints. */
export function DigichatWordmark() {
  return (
    <span className="digichat-wordmark" style={{ display: "inline-block", width: 140, height: 20 }}>
      <HeroBanner def={DIGICHAT} live={false} />
    </span>
  );
}
