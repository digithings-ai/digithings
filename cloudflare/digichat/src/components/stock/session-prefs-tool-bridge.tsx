"use client";

import { useEffect, useRef } from "react";
import { useAuiState } from "@assistant-ui/react";
import { useEmbedChatPrefsOptional } from "@/components/stock/embed-chat-prefs";
import {
  applySessionTool,
  sessionToolCallsFromMessages,
} from "@/components/stock/session-prefs-tools";

/** Applies digigraph session_* tool calls to EmbedChatPrefsApi. */
export function SessionPrefsToolBridge() {
  const api = useEmbedChatPrefsOptional();
  const messages = useAuiState((s) => s.thread.messages);
  const seen = useRef(new Set<string>());
  useEffect(() => {
    if (!api) return;
    for (const call of sessionToolCallsFromMessages(messages as unknown[])) {
      if (seen.current.has(call.id)) continue;
      seen.current.add(call.id);
      applySessionTool(call.name, call.args, api);
    }
  }, [api, messages]);
  return null;
}
