"use client";
import { useCallback, useEffect, useRef, useState } from "react";

/**
 * useStackChat — the shared chat engine behind both the landing quick-ask
 * (StackChat) and the full-screen DigiChat page. Render-agnostic: it owns the
 * transcript, streaming, abort, and error state, but emits no UI — each surface
 * draws its own (compact terminal bar vs. full session).
 *
 * It POSTs the running transcript to the Cloudflare Pages Function at
 * `/api/chat`, which full-text-searches the DigiVault architecture vault in
 * Supabase and streams an OpenRouter completion back as plain-text token deltas.
 * A non-streaming JSON response is the error path (missing key, rate limit, …).
 *
 * Latest transcript is mirrored in a ref so `send` stays stable and never reads a
 * stale closure — important when the DigiChat page seeds a handoff transcript and
 * immediately sends a pending question on mount.
 */
export interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

export interface UseStackChat {
  messages: ChatMessage[];
  busy: boolean;
  error: string | null;
  /** Append a user turn and stream the assistant reply. No-op while busy or empty. */
  send: (question: string) => Promise<void>;
  /** Abort the in-flight stream and keep whatever streamed so far. */
  stop: () => void;
  /** Clear the transcript and any error. */
  reset: () => void;
  /** Replace the transcript wholesale (used by the cross-tab handoff). */
  seed: (messages: ChatMessage[]) => void;
}

export function useStackChat(initial: ChatMessage[] = []): UseStackChat {
  const [messages, setMessages] = useState<ChatMessage[]>(initial);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const messagesRef = useRef<ChatMessage[]>(initial);
  const abortRef = useRef<AbortController | null>(null);

  // Single funnel for transcript writes so the ref and state never diverge.
  const apply = useCallback((next: ChatMessage[]) => {
    messagesRef.current = next;
    setMessages(next);
  }, []);

  // Abort any in-flight stream on unmount.
  useEffect(() => () => abortRef.current?.abort(), []);

  const send = useCallback(
    async (question: string) => {
      const q = question.trim();
      if (!q || abortRef.current) return; // abortRef set === a stream is in flight
      setError(null);

      const base: ChatMessage[] = [...messagesRef.current, { role: "user", content: q }];
      apply([...base, { role: "assistant", content: "" }]); // placeholder we stream into
      setBusy(true);

      const controller = new AbortController();
      abortRef.current = controller;
      try {
        const res = await fetch("/api/chat", {
          method: "POST",
          headers: { "content-type": "application/json" },
          body: JSON.stringify({ messages: base }),
          signal: controller.signal,
        });

        // Non-streaming JSON => an error path (missing key, rate limit, etc.).
        const ctype = res.headers.get("content-type") ?? "";
        if (!res.ok || ctype.includes("application/json")) {
          let msg = `request failed (${res.status})`;
          try {
            const data = await res.json();
            msg = data.error
              ? data.error === "chat not configured"
                ? "chat not configured on this deployment"
                : String(data.error)
              : msg;
          } catch {
            /* keep generic msg */
          }
          apply(base); // drop the placeholder; surface the error line instead
          setError(msg);
          return;
        }

        const reader = res.body?.getReader();
        if (!reader) throw new Error("no response stream");
        const decoder = new TextDecoder();
        let acc = "";
        for (;;) {
          const { done, value } = await reader.read();
          if (done) break;
          acc += decoder.decode(value, { stream: true });
          apply([...base, { role: "assistant", content: acc }]);
        }
        if (!acc.trim()) {
          apply(base);
          setError("no answer returned — try rephrasing");
        }
      } catch (e) {
        if ((e as Error).name === "AbortError") return; // keep partial text
        apply([...messagesRef.current.slice(0, -1)]); // drop the empty placeholder
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
