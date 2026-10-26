/**
 * The client's screen layout, in one place, so the frame exporter cannot
 * drift from what the client paints (DIG-2698).
 */

/** Rows the DIGICHAT wordmark paints at the top of the screen. */
export const WORDMARK_ROWS = 5;

/**
 * The width of the session rail, in columns. The rail carries the session
 * list; the chat thread is painted to its right.
 */
export function railColumns(width: number): number {
  return Math.min(28, Math.max(18, Math.floor(width * 0.28)));
}
