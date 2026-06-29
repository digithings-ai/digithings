"use client";
/**
 * Homepage `#pipeline` — linear research → execution walkthrough.
 * Steps slide in from alternating sides; the center timeline fills on scroll
 * (same accent-bar language as the hero scroll cue).
 */
import { useEffect, useRef } from "react";
import { Reveal } from "@digithings/web";

const clamp = (v: number, a: number, b: number) => Math.max(a, Math.min(b, v));

const FLOW: { n: string; title: string; body: string; tool: string }[] = [
  {
    n: "01",
    title: "Research",
    body: "Ask in plain language. An LLM research loop pulls free macro and market data and proposes directions to test.",
    tool: "chat · LLM",
  },
  {
    n: "02",
    title: "Indicators",
    body: "Compose validated indicators — moving averages, RSI, ADF, DPSD — from the shared, unit-tested library.",
    tool: "indicators lib",
  },
  {
    n: "03",
    title: "Strategy",
    body: "Wire indicators into a rules-based strategy with explicit entries, exits, sizing, and risk.",
    tool: "strategy spec",
  },
  {
    n: "04",
    title: "Signals",
    body: "Generate entry and exit signals across historical bars — deterministic and reproducible.",
    tool: "signal gen",
  },
  {
    n: "05",
    title: "Optimize",
    body: "Search the parameter space with Optuna; walk-forward windows guard against overfitting.",
    tool: "Optuna",
  },
  {
    n: "06",
    title: "Backtest",
    body: "Replay on a NautilusTrader core — Pine-faithful fills, full trade ledger, and a tearsheet.",
    tool: "NautilusTrader",
  },
  {
    n: "07",
    title: "Execution",
    body: "Promote up the ladder: backtest → paper → loopback → live. Every rung is a human gate.",
    tool: "Kairos · gated",
  },
];

export function ResearchPipeline() {
  const stepsRef = useRef<HTMLOListElement>(null);
  const trackFillRef = useRef<HTMLDivElement>(null);
  const stepRefs = useRef<(HTMLLIElement | null)[]>([]);

  useEffect(() => {
    const list = stepsRef.current;
    const fill = trackFillRef.current;
    const els = stepRefs.current.filter(Boolean) as HTMLLIElement[];
    if (!list || !fill || !els.length) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const io = new IntersectionObserver(
      (entries) =>
        entries.forEach((e) => {
          if (e.isIntersecting) e.target.classList.add("is-visible");
        }),
      { rootMargin: "-8% 0px -10% 0px", threshold: 0.12 },
    );
    els.forEach((el) => io.observe(el));

    const syncFill = () => {
      if (reduced) {
        fill.style.height = "100%";
        return;
      }
      const rect = list.getBoundingClientRect();
      const vh = window.innerHeight;
      const start = vh * 0.42;
      const end = rect.height - vh * 0.12;
      const progress = end > 0 ? clamp((start - rect.top) / end, 0, 1) : 0;
      fill.style.height = `${progress * 100}%`;
    };

    syncFill();
    window.addEventListener("scroll", syncFill, { passive: true });
    window.addEventListener("resize", syncFill, { passive: true });

    if (reduced) els.forEach((el) => el.classList.add("is-visible"));

    return () => {
      io.disconnect();
      window.removeEventListener("scroll", syncFill);
      window.removeEventListener("resize", syncFill);
    };
  }, []);

  return (
    <section className="section dqpipe" id="pipeline">
      <div className="wrap">
        <Reveal className="dq-sechead">
          <div className="dq-eyebrow">{"// the pipeline"}</div>
          <h2 className="dq-title">Research in, orders out — in a straight line.</h2>
          <p className="dq-sub">
            digiquant is not a hub of services routing messages around; it&rsquo;s a linear research
            workflow. You start in a chat, and each stage hands its output to the next until a
            strategy is ready to run.
          </p>
        </Reveal>

        <div className="dqpipe-steps-wrap">
          <div className="dqpipe-track" aria-hidden="true">
            <div className="dqpipe-track-fill" ref={trackFillRef} />
          </div>
          <ol
            className="dqpipe-steps"
            aria-label="digiquant research-to-execution pipeline"
            ref={stepsRef}
          >
            {FLOW.map((s, i) => (
            <li
              key={s.n}
              className={`dqpipe-step${i === FLOW.length - 1 ? " is-exec" : ""}${i % 2 === 1 ? " is-right" : ""}`}
              ref={(el) => {
                stepRefs.current[i] = el;
              }}
            >
              <span className="dqpipe-rail" aria-hidden="true" />
              <div className="dqpipe-card">
                <span className="dq-flow-n">{s.n}</span>
                <h3>{s.title}</h3>
                <p>{s.body}</p>
                <span className="dq-flow-tool">{s.tool}</span>
              </div>
            </li>
            ))}
          </ol>
        </div>
      </div>
    </section>
  );
}
