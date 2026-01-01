/**
 * Fill thresholds shared by the usage meter and the context meter.
 *
 * One scale for both bars: amber once more than half is spent, orange past
 * four fifths, red past nine tenths. The colours themselves live in
 * `chat-digichat.css` (`--warn` / `--danger`, mixed for the middle band), so
 * a theme restyle never has to touch this module.
 */
export const METER_WARN_AT = 0.6;
export const METER_HOT_AT = 0.8;
export const METER_CRITICAL_AT = 0.9;

export type MeterTone = "" | "is-warn" | "is-hot" | "is-critical";

/**
 * The tone class for a fill ratio. Zero and anything non-finite stay
 * untoned: an empty bar is not "nearly full", and a bar with no denominator
 * must not borrow a warning colour.
 */
export function meterTone(ratio: number): MeterTone {
  if (!Number.isFinite(ratio) || ratio <= 0) return "";
  if (ratio >= METER_CRITICAL_AT) return "is-critical";
  if (ratio >= METER_HOT_AT) return "is-hot";
  if (ratio >= METER_WARN_AT) return "is-warn";
  return "";
}
