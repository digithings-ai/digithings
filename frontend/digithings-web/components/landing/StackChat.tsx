"use client";
import { useEffect, useRef, useState } from "react";

/**
 * "Ask about the stack" — a read-only docs Q&A chat that lives in the right-hand
 * panel of the module manifest, under the `digithings show <module>` output.
 *
 * It POSTs the running transcript to the Cloudflare Pages Function at
 * `/api/chat`, which runs BM25 retrieval over the committed digivault KB and
 * streams an OpenRouter free-pool completion back as plain-text token deltas.
 * We render those tokens live. Terminal aesthetic via the existing `.dt-*` /
 * `.dtc-*` tokens; theme-aware and keyboard accessible. If the deployment has
 * no OpenRouter key the Function returns a JSON error and we show a friendly
 * "chat not configured" line instead of a thread.
 */

interface ChatMessage {
  role: "user" | "assistant";
  content: string;
}

const SUGGESTIONS = [
  "What is DigiQuant?",
  "How does auth work?",
  "What does Olympus do?",
];

export function StackChat() {
  const [messages, setMessages] = useState<ChatMessage[]>([]);
  const [input, setInput] = useState("");
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const threadRef = useRef<HTMLDivElement>(null);
  const abortRef = useRef<AbortController | null>(null);

  // Keep the newest tokens in view as they stream.
  useEffect(() => {
    const el = threadRef.current;
    if (el) el.scrollTop = el.scrollHeight;
  }, [messages, busy]);

  // Abort any in-flight stream on unmount.
  useEffect(() => () => abortRef.current?.abort(), []);

  async function send(question: string) {
    const q = question.trim();
    if (!q || busy) return;
    setError(null);
    setInput("");

    const next: ChatMessage[] = [...messages, { role: "user", content: q }];
    // Add an empty assistant turn we append streamed tokens into.
    setMessages([...next, { role: "assistant", content: "" }]);
    setBusy(true);

    const controller = new AbortController();
    abortRef.current = controller;

    try {
      const res = await fetch("/api/chat", {
        method: "POST",
        headers: { "content-type": "application/json" },
        body: JSON.stringify({ messages: next }),
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
        // Drop the placeholder assistant turn; surface the error line instead.
        setMessages(next);
        setError(msg);
        return;
      }

      // Stream plain-text token deltas into the last assistant message.
      const reader = res.body?.getReader();
      if (!reader) throw new Error("no response stream");
      const decoder = new TextDecoder();
      let acc = "";
      for (;;) {
        const { done, value } = await reader.read();
        if (done) break;
        acc += decoder.decode(value, { stream: true });
        setMessages([...next, { role: "assistant", content: acc }]);
      }
      if (!acc.trim()) {
        setMessages(next);
        setError("no answer returned — try rephrasing");
      }
    } catch (e) {
      if ((e as Error).name === "AbortError") return;
      setMessages(next);
      setError(`network error: ${(e as Error).message}`);
    } finally {
      setBusy(false);
      abortRef.current = null;
    }
  }

  function onSubmit(e: React.FormEvent) {
    e.preventDefault();
    void send(input);
  }

  const empty = messages.length === 0;

  return (
    <div className="dtc">
      <div className="dtc-head">
        <span className="dt-mh-prompt">$</span> digithings ask
        <span className="dt-out-dim"> · docs Q&amp;A over the digivault</span>
      </div>

      <div className="dtc-thread" ref={threadRef} aria-live="polite" aria-atomic="false">
        {empty && !error ? (
          <div className="dtc-empty">
            <p className="dt-out-dim">
              Ask about the stack — modules, ports, auth, orchestration. Answers come
              only from the published docs.
            </p>
            <div className="dtc-suggest">
              {SUGGESTIONS.map((s) => (
                <button
                  key={s}
                  type="button"
                  className="dtc-chip"
                  onClick={() => void send(s)}
                  disabled={busy}
                >
                  {s}
                </button>
              ))}
            </div>
          </div>
        ) : (
          <ul className="dtc-msgs">
            {messages.map((m, i) => {
              const streaming =
                busy && m.role === "assistant" && i === messages.length - 1;
              return (
                <li key={i} className={`dtc-msg dtc-${m.role}`}>
                  <span className="dtc-who" aria-hidden="true">
                    {m.role === "user" ? ">" : "·"}
                  </span>
                  <span className="dtc-body">
                    {m.content}
                    {streaming && <span className="dt-cur" />}
                    {streaming && !m.content && (
                      <span className="dt-out-dim">retrieving…</span>
                    )}
                  </span>
                </li>
              );
            })}
          </ul>
        )}
        {error && (
          <p className="dtc-error" role="alert">
            {error}
          </p>
        )}
      </div>

      <form className="dtc-form" onSubmit={onSubmit}>
        <span className="dt-mh-prompt" aria-hidden="true">
          $
        </span>
        <input
          className="dtc-input"
          type="text"
          value={input}
          onChange={(e) => setInput(e.target.value)}
          placeholder="ask about the stack…"
          aria-label="Ask about the DigiThings stack"
          disabled={busy}
          autoComplete="off"
          maxLength={500}
        />
        <button
          className="dtc-send"
          type="submit"
          disabled={busy || !input.trim()}
          aria-label="Send question"
        >
          {busy ? "…" : "↵"}
        </button>
      </form>
    </div>
  );
}
