/**
 * Pure geometry for HorizontalScrollTrack — framework-free so it unit-tests
 * without a DOM (the component wraps these with refs, observers and motion
 * values). All x values are "distance the track has travelled left, in px".
 */

/** The pin is active only at this width and up (with motion allowed). */
export const TRACK_MIN_WIDTH = 960;

/** Clamp a number into [lo, hi]. */
export function clamp(n: number, lo: number, hi: number): number {
  return Math.min(hi, Math.max(lo, n));
}

/** How far the track must travel: its content width minus the viewport. */
export function trackTravel(contentWidth: number, viewportWidth: number): number {
  return Math.max(0, contentWidth - viewportWidth);
}

/**
 * The runway's height: the pin's own height plus the horizontal travel, so one
 * px of vertical scroll is exactly one px of horizontal travel and the runway
 * always tracks the content width (the #1198 lesson — never a hardcoded vh).
 */
export function runwayHeight(pinHeight: number, travel: number): number {
  return Math.round(pinHeight + travel);
}

/** Index of the item whose leading edge is nearest `x` (offsets ascending). */
export function nearestIndex(offsets: readonly number[], x: number): number {
  if (offsets.length === 0) return 0;
  let best = 0;
  let bestDistance = Number.POSITIVE_INFINITY;
  offsets.forEach((offset, i) => {
    const d = Math.abs(offset - x);
    if (d < bestDistance) {
      bestDistance = d;
      best = i;
    }
  });
  return best;
}

/**
 * Where the track should travel to so a focused item is revealed, or null when
 * it is already fully inside the viewport (no scroll needed).
 */
export function focusTargetX(args: {
  itemLeft: number;
  itemWidth: number;
  currentX: number;
  viewportWidth: number;
  travel: number;
}): number | null {
  const { itemLeft, itemWidth, currentX, viewportWidth, travel } = args;
  const visible = itemLeft >= currentX && itemLeft + itemWidth <= currentX + viewportWidth;
  if (visible) return null;
  return clamp(itemLeft, 0, travel);
}

/** Document scrollTop that puts the track at travel `x` (1px : 1px). */
export function scrollTopForX(args: {
  runwayTopInDocument: number;
  pinTop: number;
  x: number;
  travel: number;
}): number {
  const { runwayTopInDocument, pinTop, x, travel } = args;
  return runwayTopInDocument - pinTop + clamp(x, 0, travel);
}
