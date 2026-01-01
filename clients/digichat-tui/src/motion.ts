import motion from "../../../packages/design/motion.json";

/** Frame clocks from the shared motion tokens (ADR D6), in milliseconds. */
export const FRAME = motion.frame;

/** Spinner glyph drawn in place of the braille cycle under reduced motion. */
export const STILL_SPINNER = "·";

/**
 * `DIGI_REDUCED_MOTION=1` (or `NO_MOTION=1`) draws every animation at its
 * final frame: wordmark built with no glint, full welcome text, steady caret,
 * static spinner.
 */
export function reducedMotion(env: Record<string, string | undefined> = process.env): boolean {
  return on(env.DIGI_REDUCED_MOTION) || on(env.NO_MOTION);
}

function on(raw: string | undefined): boolean {
  if (raw == null) return false;
  const value = raw.trim().toLowerCase();
  return value !== "" && value !== "0" && value !== "false";
}
