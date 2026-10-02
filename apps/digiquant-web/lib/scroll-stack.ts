/** Scroll maths for a pinned stack of cards that slide in one after another.
 *
 *  A tall "runway" holds a sticky stage. `top` is the runway's top edge relative to the pin line
 *  (the stage's `top`): positive while the runway is still arriving, zero when the stage pins,
 *  then increasingly negative as you scroll through it. */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));

export const easeOutCubic = (t: number) => 1 - Math.pow(1 - clamp01(t), 3);

/** Overall 0..1 progress. It starts `lead` px before the stage pins, so the first card is
 *  already moving as the band arrives, and reaches 1 when the stage is about to unpin. */
export function runwayProgress(top: number, runwayH: number, stageH: number, lead: number): number {
  const total = runwayH - stageH + lead;
  if (total <= 0) return 1;
  return clamp01((lead - top) / total);
}

/** Eased 0..1 progress of card `index` of `count`. Each card owns a `window` slice of the
 *  overall progress; the slices are staggered so the last one ends exactly at 1 and
 *  neighbours overlap. */
export function stageProgress(progress: number, index: number, count: number, window = 0.4): number {
  if (count <= 1) return easeOutCubic(progress);
  const start = (index * (1 - window)) / (count - 1);
  return easeOutCubic((progress - start) / window);
}
