"use client";
import { useCallback, useEffect, useRef, useState } from "react";
import {
  CHAT_STREAM_MIME,
  type ChatActivity,
  type ChatStreamEvent,
} from "@/lib/chatStream";

export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
  activities?: ChatActivity[];
}

export interface UseStackChat {
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  send: (question: string) => Promise<void>;
  stop: () => void;
  reset: () => void;
  seed: (messages: ChatMessage[]) => void;
}

function foldEvent(
  activities: ChatActivity[],
  content: string,
  ev: ChatStreamEvent,
): { activities: ChatActivity[]; content: string } {
  switch (ev.type) {
    case "status":
      return { activities: [...activities, { kind: "status", message: ev.message }], content };
    case "tool_call":
      return {
        activities: [...activities, { kind: "tool_call", name: ev.name, query: ev.query }],
        content,
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
        };
      }
      return { activities: [...activities, { kind: "reasoning", text: ev.delta }], content };
    }
    case "content":
      return { activities, content: content + ev.delta };
    default:
      return { activities, content };
  }
}

export function useStackChat(initial: ChatMessage[] = []): UseStackChat {
  const [messages, setMessages] = useState<ChatMessage[]>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesRef = useRef<ChatMessage[]>(initial);
  const abortRef = useRef<AbortController | null>(null);

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

      const base: ChatMessage[] = [...messagesRef.current, { role: "user", content: q }];
      apply([...base, { role: "assistant", content: "" }]);
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;
      let activities: ChatActivity[] = [];
      let content = "";

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

      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json", accept: CHAT_STREAM_MIME },
          body: JSON.stringify({ messages: base }),
          signal: controller.signal,
        });

        const ctype = res.headers.get("content-type") ?? "";
        if (!res.ok || ctype.includes("application/json")) {
          let msg = `request failed (${res.status})`;
          try {
            const data = (await res.json()) as { error?: string };
            if (data.error === "chat not configured") {
              msg = "chat not configured on this deployment";
            } else if (data.error) {
              msg = String(data.error);
            }
          } catch {
            /* keep generic */
          }
          apply(base);
          setError(msg);
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
            ({ activities, content } = foldEvent(activities, content, ev));
            flush();
          }
        }

        if (!content.trim()) {
          apply(base);
          setError("no answer returned — try rephrasing");
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
    setBusy(false);
  }, [apply]);

  const seed = useCallback(
    (next: ChatMessage[]) => {
      setError(null);
      apply(next);
    },
    [apply],
  );

  return { messages, busy, error, send, stop, reset, seed };
}
