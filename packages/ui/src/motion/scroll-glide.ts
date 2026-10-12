/**
 * Skip-through / rest glide for a pinned scrolly section.
 *
 * The page scroll stays in charge. These helpers never return a scroll offset:
 * while the reader is moving, the section shows the scroll-linked pose as-is
 * (skip-through). Once the page has been still, the camera may ease from that
 * live pose back onto the narrated boxes. A glide that is already more than
 * half done is left where the reader stopped — rewinding it would fight the
 * skip, and the page is not pulled to finish the beat.
 */

const clamp01 = (n: number): number => Math.max(0, Math.min(1, n));

/** Quiet gap after the last scroll sample before a rest glide may start. */
export const REST_QUIET_MS = 180;

/** How long the camera takes to settle onto the parked boxes. */
export const REST_GLIDE_MS = 520;

/** Below this the camera is already on the narrated boxes. */
export const REST_PARKED_GLIDE = 0.02;

/**
 * At or above this the reader has committed to the next beat. Settling would
 * rewind the picture under a stationary page.
 */
export const REST_COMMIT_GLIDE = 0.5;

export interface RestGlideInput {
  /** Milliseconds since scroll position last changed. */
  quietMs: number;
  /** Scroll-linked camera blend, 0 parked on this beat and 1 on the next. */
  liveGlide: number;
  quietThreshold?: number;
}

/**
 * Whether the camera should ease back to the parked boxes. False while the
 * page is still moving, when the beat is already parked, and when the glide
 * is committed — those stay with the page scroll.
 */
export function shouldStartRestGlide(input: RestGlideInput): boolean {
  const quiet = input.quietThreshold ?? REST_QUIET_MS;
  if (input.quietMs < quiet) return false;
  const live = clamp01(input.liveGlide);
  return live > REST_PARKED_GLIDE && live < REST_COMMIT_GLIDE;
}

/** Smoothstep progress of a rest glide, 0 at the start and 1 at `durationMs`. */
export function restBlendAmount(elapsedMs: number, durationMs = REST_GLIDE_MS): number {
  if (durationMs <= 0) return 1;
  const t = clamp01(elapsedMs / durationMs);
  return t * t * (3 - 2 * t);
}

/**
 * The glide the camera should paint. `blend` 0 is the live scroll pose;
 * `blend` 1 is the parked pose of the narrated beat.
 */
export function applyRestBlend(liveGlide: number, blend: number): number {
  return clamp01(liveGlide) * (1 - clamp01(blend));
}
