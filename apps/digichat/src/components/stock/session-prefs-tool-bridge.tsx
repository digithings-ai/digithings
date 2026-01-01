"use client";

import { useEffect, useRef } from "react";
import { useAuiState } from "@assistant-ui/react";
import { useEmbedChatPrefsOptional } from "@digithings/ui/chat/stock";
import {
  applySessionTool,
  sessionToolCallsFromMessages,
} from "@/components/stock/session-prefs-tools";

type BridgeMessage = { id?: unknown; status?: { type?: unknown } };

/**
 * Applies digigraph session_* tool calls to EmbedChatPrefsApi, the same
 * state the slash palette writes. A call applies once, after its result
 * arrives, and only when the server did not refuse it (ok:false). Only calls
 * from a reply streamed while this chat is open apply: a reloaded thread does
 * not replay its old setting changes.
 */
export function SessionPrefsToolBridge() {
  const api = useEmbedChatPrefsOptional();
  const messages = useAuiState((s) => s.thread.messages);
  const seen = useRef(new Set<string>());
  const live = useRef(new Set<string>());
  useEffect(() => {
    if (!api) return;
    for (const msg of messages as unknown as BridgeMessage[]) {
      if (msg?.status?.type === "running" && msg.id != null) live.current.add(String(msg.id));
    }
    const liveMessages = (messages as unknown as BridgeMessage[]).filter(
      (msg) => msg?.id != null && live.current.has(String(msg.id)),
    );
    for (const call of sessionToolCallsFromMessages(liveMessages as unknown[])) {
      if (!call.done || seen.current.has(call.id)) continue;
      seen.current.add(call.id);
      if (call.refused) continue;
      applySessionTool(call.name, { ...call.args, ...(call.prefs ?? {}) }, api);
    }
  }, [api, messages]);
  return null;
}
