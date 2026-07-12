"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  CHAT_STREAM_MIME,
  type ChatActivity,
  type ChatStreamEvent,
} from "@/lib/chatStream";
import type { ProviderSettings as ProviderConfig } from "@/lib/providerSettings";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  activities?: ChatActivity[];
}

export interface UseStackChat {
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  quotaPrompt: boolean;
  send: (question: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
  seed: (messages: ChatMessage[]) => void;
  clearQuotaPrompt: () => void;
}

function foldEvent(
  activities: ChatActivity[],
  content: string,
  ev: ChatStreamEvent,
): { activities: ChatActivity[]; content: string; quotaPrompt: boolean } {
  switch (ev.type) {
    case "status":
      return {
        activities: [...activities, { kind: "status", message: ev.message }],
        content,
        quotaPrompt: false,
      };
    case "tool_call":
      return {
        activities: [...activities, { kind: "tool_call", name: ev.name, query: ev.query }],
        content,
        quotaPrompt: false,
      };
    case "tool_result":
      return {
        activities: [
          ...activities,
          {
            kind: "tool_result",
            name: ev.name,
            query: ev.query,
            hits: ev.hits,
            count: ev.count,
          },
        ],
        content,
        quotaPrompt: false,
      };
    case "reasoning": {
      const last = activities.at(-1);
      if (last?.kind === "reasoning") {
        return {
          activities: [
            ...activities.slice(0, -1),
            { kind: "reasoning", text: last.text + ev.delta },
          ],
          content,
          quotaPrompt: false,
        };
      }
      return {
        activities: [...activities, { kind: "reasoning", text: ev.delta }],
        content,
        quotaPrompt: false,
      };
    }
    case "content":
      return { activities, content: content + ev.delta, quotaPrompt: false };
    case "quota_exhausted":
      return { activities, content, quotaPrompt: true };
    default:
      return { activities, content, quotaPrompt: false };
  }
}

export function useStackChat(
  initial: ChatMessage[] = [],
  provider?: ProviderConfig,
): UseStackChat {
  const [messages, setMessages] = useState<ChatMessage[]>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [quotaPrompt, setQuotaPrompt] = useState(false);
  const messagesRef = useRef<ChatMessage[]>(initial);
  const abortRef = useRef<AbortController | null>(null);
  const providerRef = useRef(provider);
  providerRef.current = provider;

  const apply = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || abortRef.current) return;
      setError(null);
      setQuotaPrompt(false);

      const base: ChatMessage[] = [...messagesRef.current, { role: "user", content: q }];
      apply([...base, { role: "assistant", content: "" }]);
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;
      let activities: ChatActivity[] = [];
      let content = "";
      let sawQuota = false;

      const flush = () => {
        apply([
          ...base,
          {
            role: "assistant",
            content,
            activities: activities.length ? activities : undefined,
          },
        ]);
      };

      const cfg = providerRef.current;
      const headers: Record<string, string> = {
        "content-type": "application/json",
        accept: CHAT_STREAM_MIME,
      };
      const body: { messages: ChatMessage[]; model?: string } = { messages: base };
      if (cfg?.isSet) {
        headers["X-BYOK-Key"] = cfg.apiKey;
        headers["X-BYOK-Provider"] = cfg.provider;
        headers["X-BYOK-Model"] = cfg.model;
        body.model = cfg.model;
      }

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers,
          body: JSON.stringify(body),
          signal: controller.signal,
        });

        const ctype = res.headers.get("content-type") ?? "";
        if (!res.ok || ctype.includes("application/json")) {
          let msg = `request failed (${res.status})`;
          try {
            const data = (await res.json()) as { error?: string };
            if (data.error === "chat not configured") {
              msg = "chat not configured — add your own API key in settings";
            } else if (data.error) {
              msg = String(data.error);
            }
          } catch {
            /* keep generic */
          }
          apply(base);
          setError(msg);
          if (!cfg?.isSet) setQuotaPrompt(true);
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error("no response stream");
        const decoder = new TextDecoder();
        let buf = "";

        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          buf += decoder.decode(value, { stream: true });
          let nl: number;
          while ((nl = buf.indexOf("\n")) !== -1) {
            const line = buf.slice(0, nl).trim();
            buf = buf.slice(nl + 1);
            if (!line) continue;
            let ev: ChatStreamEvent;
            try {
              ev = JSON.parse(line) as ChatStreamEvent;
            } catch {
              continue;
            }
            if (ev.type === "error") {
              apply(base);
              setError(ev.message);
              return;
            }
            if (ev.type === "done") break;
            const folded = foldEvent(activities, content, ev);
            activities = folded.activities;
            content = folded.content;
            if (folded.quotaPrompt) sawQuota = true;
            flush();
          }
        }

        if (sawQuota) setQuotaPrompt(true);

        if (!content.trim()) {
          apply(base);
          setError("no answer returned — try rephrasing");
          if (!cfg?.isSet) setQuotaPrompt(true);
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") return;
        apply([...messagesRef.current.slice(0, -1)]);
        setError(`network error: ${(e as Error).message}`);
      } finally {
        setBusy(false);
        abortRef.current = null;
      }
    },
    [apply],
  );

  const stop = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    setBusy(false);
  }, []);

  const reset = useCallback(() => {
    abortRef.current?.abort();
    abortRef.current = null;
    apply([]);
    setError(null);
    setQuotaPrompt(false);
    setBusy(false);
  }, [apply]);

  const seed = useCallback(
    (next: ChatMessage[]) => {
      setError(null);
      setQuotaPrompt(false);
      apply(next);
    },
    [apply],
  );

  const clearQuotaPrompt = useCallback(() => setQuotaPrompt(false), []);

  return { messages, busy, error, quotaPrompt, send, stop, reset, seed, clearQuotaPrompt };
}
