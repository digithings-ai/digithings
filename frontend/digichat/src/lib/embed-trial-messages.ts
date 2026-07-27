/**
 * postMessage contract for the trial-form gate (see the design spec's Global
 * Constraints). Two minimal `{ type }` messages, strict origin checks in both
 * directions, never targetOrigin "*". No credentials cross the boundary.
 */

export const GATED_MESSAGE = { type: "datatap:gated" } as const;
export const UNLOCKED_MESSAGE_TYPE = "datatap:unlocked";

/** True only for a well-formed unlock message from the exact known parent origin. */
export function isUnlockedMessage(
  event: MessageEvent,
  parentOrigin: string | undefined,
): boolean {
  if (!parentOrigin) return false;
  if (event.origin !== parentOrigin) return false;
  const data = event.data as { type?: unknown } | null;
  return !!data && data.type === UNLOCKED_MESSAGE_TYPE;
}
