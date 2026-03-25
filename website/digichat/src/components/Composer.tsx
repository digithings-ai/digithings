import { useRef, useState, useEffect } from "react";

interface Props {
  onSend: (text: string) => void;
  onAbort: () => void;
  busy: boolean;
}

export function Composer({ onSend, onAbort, busy }: Props) {
  const [text, setText] = useState("");
  const taRef = useRef<HTMLTextAreaElement>(null);
  const canSend = text.trim().length > 0 && !busy;

  // Auto-resize textarea
  useEffect(() => {
    const ta = taRef.current;
    if (!ta) return;
    ta.style.height = "auto";
    ta.style.height = Math.min(ta.scrollHeight, 160) + "px";
  }, [text]);

  // Escape key aborts streaming
  useEffect(() => {
    function onKey(e: KeyboardEvent) {
      if (e.key === "Escape" && busy) onAbort();
    }
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [busy, onAbort]);

  function handleKeyDown(e: React.KeyboardEvent<HTMLTextAreaElement>) {
    if (e.key === "Enter" && !e.shiftKey) {
      e.preventDefault();
      if (canSend) submit();
    }
  }

  function submit() {
    const t = text.trim();
    if (!t) return;
    setText("");
    onSend(t);
  }

  return (
    <div className="flex-shrink-0 pb-5 pt-2 animate-[composer-in_0.5s_cubic-bezier(0.2,0.8,0.2,1)_0.15s_both]">
      <form
        onSubmit={(e) => {
          e.preventDefault();
          submit();
        }}
        className="flex items-end gap-2.5 px-3 py-2.5 rounded-2xl border border-white/[0.1] bg-[rgba(10,10,10,0.5)] backdrop-blur-xl shadow-[0_-8px_40px_rgba(0,0,0,0.4)]"
      >
        <label htmlFor="composer-input" className="sr-only">
          Message
        </label>
        <textarea
          ref={taRef}
          id="composer-input"
          rows={1}
          value={text}
          onChange={(e) => setText(e.target.value)}
          onKeyDown={handleKeyDown}
          disabled={busy}
          placeholder="Ask anything about research, RAG, backtests…"
          maxLength={32000}
          className="flex-1 min-h-[40px] max-h-[160px] resize-none border-none bg-transparent text-[#e6e6e6] font-sans text-[0.92rem] leading-relaxed py-1 px-1 outline-none placeholder:text-[#555] disabled:opacity-50"
        />

        {busy ? (
          <button
            type="button"
            onClick={onAbort}
            className="shrink-0 w-9 h-9 rounded-xl border border-white/[0.12] bg-white/[0.05] text-[#a3a3a3] hover:bg-white/[0.1] hover:text-[#e6e6e6] flex items-center justify-center transition-all cursor-pointer"
            aria-label="Stop generation"
            title="Stop (Esc)"
          >
            {/* Stop square */}
            <svg viewBox="0 0 16 16" fill="currentColor" className="w-3.5 h-3.5">
              <rect x="3" y="3" width="10" height="10" rx="1.5" />
            </svg>
          </button>
        ) : (
          <button
            type="submit"
            disabled={!canSend}
            className={`shrink-0 w-9 h-9 rounded-xl flex items-center justify-center transition-all cursor-pointer border ${
              canSend
                ? "border-[#4a90e2]/50 bg-[linear-gradient(145deg,rgba(74,144,226,0.25),rgba(255,255,255,0.06))] text-white hover:shadow-[0_0_18px_rgba(74,144,226,0.3)]"
                : "border-white/[0.08] bg-white/[0.04] text-[#555] cursor-not-allowed opacity-40"
            }`}
            aria-label="Send message"
          >
            <svg
              viewBox="0 0 24 24"
              fill="none"
              stroke="currentColor"
              strokeWidth="2"
              strokeLinecap="round"
              strokeLinejoin="round"
              className="w-4 h-4"
              aria-hidden="true"
            >
              <line x1="22" y1="2" x2="11" y2="13" />
              <polygon points="22 2 15 22 11 13 2 9 22 2" />
            </svg>
          </button>
        )}
      </form>
      <p className="text-center text-[0.68rem] text-[#444] mt-1.5">
        Enter to send · Shift+Enter for newline{busy ? " · Esc to stop" : ""}
      </p>
    </div>
  );
}
