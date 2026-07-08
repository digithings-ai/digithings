"use client";

import { useEffect, useRef } from "react";
import { useInView, useReducedMotion } from "motion/react";
import { ChatMessage, ChatStreamCursor, ChatTranscript } from "@digithings/web";

/**
 * Streaming transcript — the digichat grammar (canon §16): `>` user turn,
 * `▸` assistant turn, a folded tool-work chip, and a streaming caret that types
 * the answer token by token. Wears the digichat rose livery. Assembled from the
 * shared chat-core primitives (<ChatTranscript>/<ChatMessage>/<ChatStreamCursor>
 * from @digithings/web); the tool-work chip stays a page-local flourish
 * (.st-tool). The answer text is written straight to the DOM node (no per-frame
 * React re-render); SSR / no-JS / reduced motion all render the finished
 * transcript with no typing.
 */
const ANSWER =
  "done. PF 6.62 · win 64.91% · maxDD −59.22% — tearsheet saved to the vault.";

export function StreamTranscriptReference() {
  const reduced = useReducedMotion();
  const scopeRef = useRef<HTMLDivElement | null>(null);
  const answerRef = useRef<HTMLSpanElement | null>(null);
  const caretRef = useRef<HTMLSpanElement | null>(null);
  const inView = useInView(scopeRef, { amount: 0.4, once: true });

  useEffect(() => {
    const answer = answerRef.current;
    const caret = caretRef.current;
    if (!answer || !caret || !inView || reduced) return;
    answer.textContent = "";
    caret.style.visibility = "visible";
    let i = 0;
    const id = window.setInterval(() => {
      i += 1;
      answer.textContent = ANSWER.slice(0, i);
      if (i >= ANSWER.length) {
        window.clearInterval(id);
        caret.style.visibility = "hidden";
      }
    }, 22);
    return () => window.clearInterval(id);
  }, [inView, reduced]);

  return (
    <section className="section-block accent-digichat" ref={scopeRef}>
      <p className="kicker">{"// streaming transcript"}</p>
      <h2 className="title">The answer arrives as it&apos;s written.</h2>
      <p className="section-copy">
        The chat surface&apos;s turn grammar: a user line, an assistant line, tool work folded into
        a chip, and the response streaming in under a live caret. Markers carry the accent; tool
        work never opens on its own. Reduced motion shows the finished turn.
      </p>

      <ChatTranscript flat className="mt-[1.2rem] max-w-[640px] text-[0.78rem] leading-[2.1]">
        <ChatMessage role="user">backtest trend_xsec on ETH, last eight years</ChatMessage>
        <ChatMessage role="assistant">running it through digiquant · nautilus engine</ChatMessage>
        <div className="st-tool">
          <span className="mr-[0.55rem] text-accent">⌄</span>
          digiquant.backtest — trend_xsec · ETH-USD · 3,102 bars
          <span className="text-up">ok</span>
          <span className="text-ink-mute">412ms</span>
        </div>
        <ChatMessage role="assistant" tone="ink">
          <span ref={answerRef}>{ANSWER}</span>
          <ChatStreamCursor ref={caretRef} />
        </ChatMessage>
      </ChatTranscript>
    </section>
  );
}
