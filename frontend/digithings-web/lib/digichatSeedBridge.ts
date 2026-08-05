import type { ChatHandoff } from "./chatHandoff";

export const READY_TIMEOUT_MS = 8000;
export const CHAT_LOAD_ERROR_COPY =
  "Chat is taking too long to load. Refresh to try again.";

export function createSeedPayload(handoff: ChatHandoff) {
  return {
    type: "digichat:seed" as const,
    messages: handoff.messages.map((m) => ({ role: m.role, content: m.content })),
    pending: handoff.pending,
    ts: handoff.ts,
  };
}

export function shouldAcceptReady(event: MessageEvent, digichatOrigin: string): boolean {
  if (event.origin !== digichatOrigin) return false;
  const data = event.data as { type?: unknown } | null;
  return !!data && data.type === "digichat:ready";
}
