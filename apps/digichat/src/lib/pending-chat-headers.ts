/**
 * Per-key pending headers for the next POST /api/chat.
 *
 * Not React refs: `react-hooks/refs` forbids `.current` inside the useMemo that
 * builds AssistantChatTransport, and useChat never adopts a rebuilt transport
 * (#1339). Keyed by thread id (first-party) or embed host (iframe) so two
 * widgets cannot steal each other's slash / turn mode.
 *
 * Force-tool is send-only (#3466): hosts must clear it before regenerate/edit.
 */

import type { DigiTurnMode } from "@/lib/turn-mode";

export type PendingMutatingTurn = Exclude<DigiTurnMode, "send">;

const pendingForceByKey = new Map<string, string>();
const pendingTurnModeByKey = new Map<string, PendingMutatingTurn>();
const pendingWebSearchForceByKey = new Set<string>();

export function setPendingForceTool(key: string, tool?: string): void {
  const id = key.trim();
  if (!id) return;
  if (tool) pendingForceByKey.set(id, tool);
  else pendingForceByKey.delete(id);
}

export function takePendingForceTool(key: string): string | undefined {
  const id = key.trim();
  const tool = pendingForceByKey.get(id);
  pendingForceByKey.delete(id);
  return tool;
}

export function setPendingTurnMode(key: string, mode?: PendingMutatingTurn): void {
  const id = key.trim();
  if (!id) return;
  if (mode) pendingTurnModeByKey.set(id, mode);
  else pendingTurnModeByKey.delete(id);
}

export function takePendingTurnMode(key: string): PendingMutatingTurn | undefined {
  const id = key.trim();
  const mode = pendingTurnModeByKey.get(id);
  pendingTurnModeByKey.delete(id);
  return mode;
}

/** `/websearch query` enables web search for this send only. */
export function setPendingWebSearchForce(key: string, on = true): void {
  const id = key.trim();
  if (!id) return;
  if (on) pendingWebSearchForceByKey.add(id);
  else pendingWebSearchForceByKey.delete(id);
}

export function takePendingWebSearchForce(key: string): boolean {
  const id = key.trim();
  const on = pendingWebSearchForceByKey.has(id);
  pendingWebSearchForceByKey.delete(id);
  return on;
}

/** Set send-only force-tool before a gated `onHold` that takes it. */
export function armForceToolThenHold(
  key: string,
  tool: string,
  onHold: () => void,
): void {
  setPendingForceTool(key, tool);
  onHold();
}
