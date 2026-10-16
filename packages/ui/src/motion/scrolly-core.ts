/**
 * Pure logic for the ScrollyFeatures primitive (pinned section + progress rail).
 * Framework-free and side-effect-free so it can be unit-tested without a DOM —
 * the React hook in `./scrolly.tsx` wraps these with `useScroll` + `matchMedia`.
 *
 * Generalizes the scroll→slide mapping that `ScrollyGraph` (components/graph.tsx)
 * and digiquant-web's `PipelineScene` both hand-roll.
 */

/**
 * Map a 0..1 scroll progress to an active slide index, clamped to
 * `[0, slideCount - 1]`. `floor(progress * slideCount)` gives each slide an
 * equal dwell; progress exactly at 1 maps to the last slide (not out of range).
 */
export function progressToIndex(progress: number, slideCount: number): number {
  if (slideCount <= 0) return 0;
  const raw = Math.floor(progress * slideCount);
  return Math.max(0, Math.min(slideCount - 1, raw));
}

/**
 * Vertical scroll budget (in `vh`) for a pinned scrolly: one dwell per slide.
 * Derived from the slide count (content) rather than a hardcoded viewport
 * multiple — the #1198 lesson (a pin's scroll budget must track its content so
 * the next section can't overlap the pin and it holds up under browser zoom).
 * Consumers with tall/variable slides can pass a larger `vhPerSlide`.
 */
export function scrollyTrackHeightVh(slideCount: number, vhPerSlide = 90): number {
  return Math.max(1, slideCount) * vhPerSlide;
}

/**
 * Media query that forces the flow-layout fallback: small viewport OR
 * reduced-motion. When it matches, consumers render every slide in normal flow
 * (no pinning) — satisfying `prefers-reduced-motion: reduce` by showing all
 * slides, and giving small screens a static stepper.
 */
export const STEPPER_MEDIA_QUERY = "(max-width: 860px), (prefers-reduced-motion: reduce)";
