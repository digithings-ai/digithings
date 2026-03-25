import { useState, useRef, useCallback } from "react";
import { Config, ChatMessage } from "../types";

function randomId(): string {
  if (crypto.randomUUID) return crypto.randomUUID();
  return "id-" + Math.random().toString(36).slice(2) + Date.now().toString(36);
}

async function readSseStream(
  body: ReadableStream<Uint8Array>,
  onDelta: (chunk: string) => void,
): Promise<void> {
  const reader = body.getReader();
  const dec = new TextDecoder();
  let buffer = "";
  while (true) {
    const { done, value } = await reader.read();
    if (done) break;
    buffer += dec.decode(value, { stream: true });
    const blocks = buffer.split("\n\n");
    buffer = blocks.pop() ?? "";
    for (const block of blocks) {
      for (const line of block.split("\n")) {
        const trimmed = line.trim();
        if (!trimmed.startsWith("data:")) continue;
        const data = trimmed.slice(5).trim();
        if (data === "[DONE]") continue;
        try {
          const j = JSON.parse(data) as {
            choices?: { delta?: { content?: string } }[];
          };
          const content = j.choices?.[0]?.delta?.content;
          if (content) onDelta(content);
        } catch {
          /* ignore malformed chunk */
        }
      }
    }
  }
}

export function useChat(config: Config) {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [busy, setBusy] = useState(false);
  const sessionIdRef = useRef<string>(randomId());
  const historyRef = useRef<{ role: string; content: string }[]>([]);
  const abortRef = useRef<AbortController | null>(null);

  const sendMessage = useCallback(
    async (text: string) => {
      const userMsg: ChatMessage = {
        id: randomId(),
        role: "user",
        content: text.trim(),
      };
      const assistantId = randomId();
      const assistantMsg: ChatMessage = {
        id: assistantId,
        role: "assistant",
        content: "",
        streaming: true,
      };

      setMessages((prev) => [...prev, userMsg, assistantMsg]);
      historyRef.current.push({ role: "user", content: text.trim() });

      const headers: Record<string, string> = {
        "Content-Type": "application/json",
        "X-Session-Id": sessionIdRef.current,
      };
      if (config.apiKey) headers["Authorization"] = `Bearer ${config.apiKey}`;
      if (config.openwebuiFormat) headers["X-Response-Format"] = "openwebui";

      const body = JSON.stringify({
        model: config.model,
        messages: historyRef.current.map((m) => ({
          role: m.role,
          content: m.content,
        })),
        stream: !!config.stream,
        openwebui_format: !!config.openwebuiFormat,
        session_id: sessionIdRef.current,
      });

      abortRef.current = new AbortController();
      setBusy(true);
      let acc = "";

      const update = (content: string, opts?: { error?: boolean; streaming?: boolean }) =>
        setMessages((prev) =>
          prev.map((m) =>
            m.id === assistantId ? { ...m, content, ...opts } : m,
          ),
        );

      try {
        const res = await fetch(`${config.digigraphUrl}/v1/chat/completions`, {
          method: "POST",
          headers,
          body,
          signal: abortRef.current.signal,
        });

        if (!res.ok) {
          const errText = await res.text();
          throw new Error(errText || res.statusText || String(res.status));
        }

        if (config.stream && res.body) {
          await readSseStream(res.body, (chunk) => {
            acc += chunk;
            update(acc, { streaming: true });
          });
          update(acc, { streaming: false });
          historyRef.current.push({ role: "assistant", content: acc });
        } else {
          const data = (await res.json()) as {
            choices?: { message?: { content?: string } }[];
          };
          acc = data.choices?.[0]?.message?.content ?? JSON.stringify(data);
          historyRef.current.push({ role: "assistant", content: acc });
          update(acc, { streaming: false });
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") {
          if (acc.trim()) {
            historyRef.current.push({ role: "assistant", content: acc });
            update(acc, { streaming: false });
          } else {
            update("(stopped)", { streaming: false });
          }
        } else {
          update((e as Error).message || String(e), {
            streaming: false,
            error: true,
          });
        }
      } finally {
        abortRef.current = null;
        setBusy(false);
      }
    },
    [config],
  );

  const abort = useCallback(() => {
    abortRef.current?.abort();
  }, []);

  const newSession = useCallback(() => {
    abortRef.current?.abort();
    sessionIdRef.current = randomId();
    historyRef.current = [];
    setMessages([]);
    setBusy(false);
  }, []);

  return { messages, busy, sendMessage, abort, newSession };
}
