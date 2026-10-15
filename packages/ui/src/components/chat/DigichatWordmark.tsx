"use client";

import { DIGICHAT } from "@digithings/hero-banner/definitions";
import { HeroBanner } from "@digithings/hero-banner/web";

/** Square-pixel DIGICHAT mark, drawn from the shared hero-banner definition
 *  (`packages/hero-banner`, `DIGICHAT`: scramble 80/240/180 with a 960 hold,
 *  settled at 2000 ms, seed 0). The scramble builds once per tab
 *  (`replayLoading`); reduced motion paints the settled mark with no scramble
 *  (inside `HeroBanner`, not in CSS). The `.digichat-wordmark` wrapper keeps
 *  the existing hook for surrounding layout. */
export function DigichatWordmark() {
  return (
    <div className="digichat-wordmark">
      <HeroBanner def={DIGICHAT} replayLoading />
    </div>
  );
}
