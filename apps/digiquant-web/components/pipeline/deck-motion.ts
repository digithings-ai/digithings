/** Deck motion for the pipeline band.
 *
 *  Phone width shows one column and does not animate. From 1024px the deck shows two
 *  cards; from 1440px it shows three. While motion is allowed the scroll progress plays
 *  one sequence: the visible cards start stacked, slide apart into their slots, then each
 *  following card stacks onto the right-hand slot and the row slides left underneath it.
 *  Reduced motion never reaches this module from the runway. */

const clamp01 = (v: number) => Math.min(1, Math.max(0, v));
const easeOutCubic = (t: number) => 1 - Math.pow(1 - clamp01(t), 3);

/** Matches the Tailwind `lg` breakpoint. Two cards from here. */
export const DECK_TWO_MIN = 1024;
/** Three cards once the page is wide enough for them to stay readable. */
export const DECK_THREE_MIN = 1440;
/** Gap between seated cards, in px. Same as the static `gap-4` grid. */
export const DECK_GAP = 16;
/** Desktop, and only when the reader has not asked for reduced motion. */
export const DECK_MOTION_QUERY = `(min-width: ${DECK_TWO_MIN}px) and (prefers-reduced-motion: no-preference)`;

const STACK_Y = 16;

export function deckVisibleCount(width: number): 1 | 2 | 3 {
  if (width >= DECK_THREE_MIN) return 3;
  if (width >= DECK_TWO_MIN) return 2;
  return 1;
}

export function deckPhaseCount(count: number, visible: number): number {
  const shown = Math.max(1, Math.min(visible, Math.max(count, 1)));
  if (count <= shown) return 1;
  return 1 + (count - shown);
}

export interface DeckPose {
  x: number;
  y: number;
  opacity: number;
  z: number;
}

/** Pose of card `index` at overall progress 0..1. `cardW` and `gap` are px. */
export function deckPose(
  index: number,
  count: number,
  visible: number,
  progress: number,
  cardW: number,
  gap: number,
): DeckPose {
  const shown = Math.max(1, Math.min(visible, Math.max(count, 1)));
  const stride = cardW + gap;
  const phases = deckPhaseCount(count, shown);
  const scaled = clamp01(progress) * phases;
  const phaseIndex = scaled >= phases ? phases - 1 : Math.min(phases - 1, Math.floor(scaled));
  const local = scaled >= phases ? 1 : scaled - phaseIndex;

  if (count <= shown) {
    const t = easeOutCubic(clamp01(progress));
    return {
      x: t * index * stride,
      y: (1 - t) * index * STACK_Y,
      opacity: 1,
      z: count - index,
    };
  }

  if (phaseIndex === 0) {
    const t = easeOutCubic(local);
    if (index < shown) {
      return {
        x: t * index * stride,
        y: (1 - t) * index * STACK_Y,
        opacity: 1,
        z: count - index + 2,
      };
    }
    const order = index - shown;
    return {
      x: shown * stride + order * 12,
      y: 20 + order * STACK_Y,
      opacity: 1,
      z: count - index,
    };
  }

  const windowStart = phaseIndex - 1;
  const nextIndex = windowStart + shown;
  const stacking = local < 0.42;
  const stackT = stacking ? easeOutCubic(local / 0.42) : 1;
  const slide = stacking ? 0 : easeOutCubic((local - 0.42) / 0.58);
  const lastSlot = (shown - 1) * stride;

  if (index < windowStart) {
    return { x: -stride - 32, y: 0, opacity: 0, z: 0 };
  }

  if (index === nextIndex) {
    const fromX = shown * stride + 28;
    return {
      x: fromX + (lastSlot - fromX) * stackT,
      y: (1 - stackT) * (1 - slide) * 22,
      opacity: 1,
      z: 40,
    };
  }

  if (index > nextIndex) {
    const order = index - nextIndex;
    return {
      x: shown * stride + order * 12,
      y: 20 + order * STACK_Y,
      opacity: 1,
      z: 8 - order,
    };
  }

  const slot = index - windowStart;
  return {
    x: (slot - slide) * stride,
    y: 0,
    opacity: slot === 0 ? 1 - slide : 1,
    z: 12 - slot,
  };
}
