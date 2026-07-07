"use client";

import { useEffect, useRef } from "react";
import { useInView, useReducedMotion } from "motion/react";

/**
 * Streaming transcript — the digichat grammar (canon §16): `>` user turn,
 * `▸` assistant turn, a folded tool-work chip, and a streaming caret that types
 * the answer token by token. Wears the digichat rose livery. The answer text is
 * written straight to the DOM node (no per-frame React re-render); SSR / no-JS /
 * reduced motion all render the finished transcript with no typing.
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

      <div className="st-shell mt-[1.2rem] max-w-[640px] rounded-[12px] border border-hair bg-term-bg p-[1.1rem_1.2rem] font-mono text-[0.78rem] leading-[2.1]">
        <div className="block text-ink">
          <span className="mr-[0.55rem] text-accent">&gt;</span>
          backtest trend_xsec on ETH, last eight years
        </div>
        <div className="block text-ink-soft">
          <span className="mr-[0.55rem] text-accent">▸</span>
          running it through digiquant · nautilus engine
        </div>
        <div className="st-tool">
          <span className="mr-[0.55rem] text-accent">⌄</span>
          digiquant.backtest — trend_xsec · ETH-USD · 3,102 bars
          <span className="text-up">ok</span>
          <span className="text-ink-mute">412ms</span>
        </div>
        <div className="block text-ink">
          <span className="mr-[0.55rem] text-accent">▸</span>
          <span ref={answerRef}>{ANSWER}</span>
          <span ref={caretRef} className="st-caret" aria-hidden="true" />
        </div>
      </div>
    </section>
  );
}
