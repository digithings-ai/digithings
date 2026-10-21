/**
 * The pre-response status line (DIG-4459).
 *
 * Before the agent answers, the loading row shows the animation on its own.
 * It carries text only when the server actually told us something: a
 * `data-connection` part with a `message` ("Waking up services…", "Waiting
 * for model capacity — retrying in 8s"). A bare state such as `connecting`
 * is just the wait for a response, so it gets no text, and the client never
 * makes up a default line of its own.
 */
type MessagePartLike = {
  readonly type: string;
  readonly name?: string;
  readonly data?: unknown;
};

/** States that end the pre-response phase: any earlier message is stale. */
const SETTLED_STATES = new Set(["connected", "ready"]);

/**
 * The status text the server sent for this turn, or null. The latest
 * connection part wins; a settled state clears the line.
 */
export function connectionStatusText(
  parts: readonly MessagePartLike[],
): string | null {
  let text: string | null = null;
  for (const part of parts) {
    if (part.type !== "data" || part.name !== "connection") continue;
    const data = (part.data ?? {}) as { state?: unknown; message?: unknown };
    if (typeof data.state === "string" && SETTLED_STATES.has(data.state)) {
      text = null;
      continue;
    }
    const message =
      typeof data.message === "string" ? data.message.trim() : "";
    text = message.length > 0 ? message : null;
  }
  return text;
}
