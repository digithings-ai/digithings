/**
 * The context meter's share arithmetic, kept out of the component so it
 * can be tested without a React tree.
 *
 * Decision (DIG-4459, #5967): the provider reports only the prompt
 * total, so the system / tools / user split is an estimate. The three
 * quantities are therefore a PARTITION of that reported total, never
 * three independent estimates of it. The measured user text is clamped
 * into the total first, the flat per-tool allowance is clamped into what
 * is left, and the system prompt takes the remainder. The consequence is
 * that the three token counts always sum to the reported total, so no
 * share can print above 100 and the printed numbers always describe the
 * same turn.
 *
 * The percentages are each computed from their own token count and then
 * normalised to exactly 100 by the largest-remainder method, because
 * independent rounding can sum to 99 or 101 and a leftover-derived
 * share would then be wrong (the old leftover share went negative on a
 * rounding remainder).
 */

/** Bar segments in the context meter grid. */
export const CONTEXT_BAR_CELLS = 25;

/** Rough tokens per tool schema (name, description, JSON schema). */
export const CONTEXT_TOKENS_PER_TOOL = 220;

export type ContextMeterShares = {
  /** Token counts. They sum to the reported prompt total. */
  systemTokens: number;
  toolTokens: number;
  userTokens: number;
  /** Percentages. They sum to exactly 100 when a turn reported usage. */
  systemPct: number;
  toolPct: number;
  userPct: number;
  /** Bar cells. They sum to the used span. */
  systemCells: number;
  toolCells: number;
  userCells: number;
  /** Bar cells in the used span. */
  usedCells: number;
};

export type ContextMeterInput = {
  /** Prompt total the provider reported for the last turn, 0 when unknown. */
  input: number;
  /** Characters of user text in the thread. */
  userChars: number;
  /** Connected tool count, used for the schema estimate. */
  toolCount: number;
  /** The model's context window, in tokens. */
  window: number;
};

/** Rough tokens for the user text held in the thread. */
const userTokensFromChars = (userChars: number): number =>
  Math.round(userChars / 4);

/**
 * Round exact shares so the rounded values sum to exactly 100.
 *
 * Largest remainder: floor every share, then hand the leftover points
 * to the shares with the biggest fractional part. Each result stays
 * within one point of its exact share and no result is negative.
 */
const normaliseToHundred = (exact: readonly number[]): number[] => {
  const rounded = exact.map((value) => Math.floor(value));
  const exactTotal = exact.reduce((sum, value) => sum + value, 0);
  // Only a set of exact shares that adds up to a hundred can be
  // normalised. Anything else (no reported usage) is left alone, so the
  // leftover points are never handed out against nothing.
  if (Math.abs(exactTotal - 100) > 0.5) {
    return exact.map((value) => Math.round(value));
  }
  let leftover = 100 - rounded.reduce((sum, value) => sum + value, 0);
  if (leftover <= 0) return rounded;
  const order = exact
    .map((value, index) => ({
      index,
      fraction: value - Math.floor(value),
    }))
    .sort((a, b) => b.fraction - a.fraction || a.index - b.index);
  for (const { index } of order) {
    if (leftover <= 0) break;
    rounded[index] += 1;
    leftover -= 1;
  }
  return rounded;
};

/**
 * Split a reported prompt total into system, tools and user.
 *
 * The token counts are a partition of `input`, so they always sum to it
 * and no share can exceed 100. The percentages are each derived from
 * their own token count and normalised to exactly 100.
 */
export const computeContextShares = ({
  input,
  userChars,
  toolCount,
  window,
}: ContextMeterInput): ContextMeterShares => {
  const total = input > 0 ? input : 0;

  // Partition of the reported total: measured text first, then the flat
  // tool estimate into what is left, then the remainder is the system
  // prompt.
  const userTokens =
    total > 0 ? Math.min(userTokensFromChars(userChars), total) : 0;
  const toolTokens =
    total > 0
      ? Math.min(toolCount * CONTEXT_TOKENS_PER_TOOL, total - userTokens)
      : 0;
  const systemTokens = total - userTokens - toolTokens;

  const exact =
    total > 0
      ? [
          (userTokens / total) * 100,
          (toolTokens / total) * 100,
          (systemTokens / total) * 100,
        ]
      : [0, 0, 0];
  // With no reported usage there is nothing to normalise: the three
  // exact shares are zero, not a third of a hundred each.
  const [userPct, toolPct, systemPct] =
    total > 0 ? normaliseToHundred(exact) : [0, 0, 0];

  // The used span grows with the window ratio; inside it the three types
  // take their share of the prompt.
  const ratio = window > 0 ? Math.min(1, total / window) : 0;
  const usedCells =
    total > 0 ? Math.max(1, Math.round(ratio * CONTEXT_BAR_CELLS)) : 0;
  const systemCells = Math.min(
    usedCells,
    total > 0 ? Math.round((usedCells * systemTokens) / total) : 0,
  );
  const toolCells = Math.min(
    usedCells - systemCells,
    total > 0 ? Math.round((usedCells * toolTokens) / total) : 0,
  );
  const userCells = Math.max(0, usedCells - systemCells - toolCells);

  return {
    systemTokens,
    toolTokens,
    userTokens,
    systemPct,
    toolPct,
    userPct,
    systemCells,
    toolCells,
    userCells,
    usedCells,
  };
};
