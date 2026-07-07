"use client";

import { useState } from "react";

/**
 * Chat widgets — custom action widgets embedded in the terminal transcript: a
 * metrics grid (money colors on P&L) and interactive action cards. Interactive
 * display template.
 */

const METRICS = [
  { k: "profit factor", v: "2.31" },
  { k: "max drawdown", v: "−18.4%", tone: "down" },
  { k: "sharpe", v: "1.87" },
  { k: "win rate", v: "58%" },
];

export function ChatWidgetsReference() {
  const [decision, setDecision] = useState<"pending" | "approved" | "declined">("pending");

  return (
    <section className="section-block">
      <p className="kicker">{"// custom widgets"}</p>
      <h2 className="title">Answers you can act on.</h2>
      <p className="section-copy">
        Beyond text, the assistant emits interactive widgets — a result card with its own actions, a
        confirmation gate for anything irreversible. They&apos;re built from the same tokens as the
        rest of the surface, so a widget never looks bolted on. Live-trading actions always route
        through a human gate.
      </p>

      <div className="chat-surface mt-[1.3rem] max-w-[760px] flex flex-col gap-[0.7rem] rounded-[12px] border border-term-hair bg-term-bg px-[1.15rem] pt-[1rem] pb-[1.2rem] font-mono">
        {/* Widget 1 — backtest result card */}
        <div className="flex gap-[0.55rem] items-baseline chat-turn--assistant">
          <span className="shrink-0 font-mono text-[0.86rem] leading-[1.5] text-accent" aria-hidden="true">
            ▸
          </span>
          <div className="min-w-0 border-0 rounded-none bg-transparent p-0 text-ink-soft text-[0.88rem] leading-[1.6]">
            <article className="widget-result border border-hair rounded-[12px] bg-surface overflow-hidden">
              <header className="widget-head flex items-start justify-between gap-[1rem] px-[1rem] py-[0.85rem] border-b border-hair">
                <div>
                  <p className="m-0 mb-[0.2rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-accent">
                    backtest complete
                  </p>
                  <h4 className="widget-title m-0 font-mono text-[0.86rem] text-ink">
                    trend_xsec · ETH-USD · 8y
                  </h4>
                </div>
                <span className="shrink-0 px-[0.55rem] py-[0.2rem] rounded-full font-mono text-[0.6rem] uppercase tracking-[0.06em] bg-up/15 text-up">
                  passed
                </span>
              </header>
              <div className="widget-metrics grid grid-cols-4 gap-px bg-hair max-[560px]:grid-cols-2">
                {METRICS.map((m) => (
                  <div key={m.k} className="flex flex-col gap-[0.25rem] px-[0.9rem] py-[0.8rem] bg-surface">
                    <span className="font-mono text-[0.54rem] uppercase tracking-[0.08em] text-ink-mute">
                      {m.k}
                    </span>
                    <span className={`font-mono text-[1.1rem] tabular-nums ${m.tone === "down" ? "text-down" : "text-ink"}`}>
                      {m.v}
                    </span>
                  </div>
                ))}
              </div>
              <footer className="widget-actions flex gap-[0.6rem] px-[1rem] py-[0.8rem] border-t border-hair">
                <button type="button" className="widget-btn primary px-[1rem] py-[0.5rem] rounded-full border border-transparent font-mono text-[0.72rem] cursor-pointer bg-accent">
                  View tearsheet
                </button>
                <button type="button" className="widget-btn ghost px-[1rem] py-[0.5rem] rounded-full border border-hair font-mono text-[0.72rem] cursor-pointer bg-transparent text-ink">
                  Save to vault
                </button>
              </footer>
            </article>
          </div>
        </div>

        {/* Widget 2 — human-approval gate */}
        <div className="flex gap-[0.55rem] items-baseline chat-turn--assistant">
          <span className="shrink-0 font-mono text-[0.86rem] leading-[1.5] text-accent" aria-hidden="true">
            ▸
          </span>
          <div className="min-w-0 border-0 rounded-none bg-transparent p-0 text-ink-soft text-[0.88rem] leading-[1.6]">
            <article className={`widget-approve state-${decision} border border-hair rounded-[12px] bg-surface overflow-hidden`}>
              <header className="widget-head flex items-start justify-between gap-[1rem] px-[1rem] py-[0.85rem] border-b border-hair">
                <div>
                  <p className="m-0 mb-[0.2rem] font-mono text-[0.58rem] uppercase tracking-[0.1em] text-accent">
                    requires approval
                  </p>
                  <h4 className="widget-title m-0 font-mono text-[0.86rem] text-ink">
                    Route live order → binance
                  </h4>
                </div>
                <span className="shrink-0 text-ink-mute" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="5" y="11" width="14" height="9" rx="2" />
                    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
                  </svg>
                </span>
              </header>
              <dl className="flex gap-[1.6rem] m-0 px-[1rem] py-[0.85rem]">
                <div className="flex flex-col gap-[0.2rem]">
                  <dt className="font-mono text-[0.56rem] uppercase tracking-[0.08em] text-ink-mute">side</dt>
                  <dd className="m-0 font-mono text-[0.92rem] tabular-nums text-up">buy</dd>
                </div>
                <div className="flex flex-col gap-[0.2rem]">
                  <dt className="font-mono text-[0.56rem] uppercase tracking-[0.08em] text-ink-mute">size</dt>
                  <dd className="m-0 font-mono text-[0.92rem] text-ink tabular-nums">0.40 BTC</dd>
                </div>
                <div className="flex flex-col gap-[0.2rem]">
                  <dt className="font-mono text-[0.56rem] uppercase tracking-[0.08em] text-ink-mute">limit</dt>
                  <dd className="m-0 font-mono text-[0.92rem] text-ink tabular-nums">63,410</dd>
                </div>
              </dl>
              {decision === "pending" ? (
                <footer className="widget-actions flex gap-[0.6rem] px-[1rem] py-[0.8rem] border-t border-hair">
                  <button
                    type="button"
                    className="widget-btn primary px-[1rem] py-[0.5rem] rounded-full border border-transparent font-mono text-[0.72rem] cursor-pointer bg-accent"
                    onClick={() => setDecision("approved")}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="widget-btn danger px-[1rem] py-[0.5rem] rounded-full border font-mono text-[0.72rem] cursor-pointer bg-transparent text-down"
                    onClick={() => setDecision("declined")}
                  >
                    Decline
                  </button>
                </footer>
              ) : (
                <p className={`flex items-center gap-[0.7rem] m-0 px-[1rem] py-[0.8rem] border-t border-hair font-mono text-[0.76rem] ${decision === "approved" ? "text-up" : "text-down"}`}>
                  {decision === "approved"
                    ? "✓ Approved — order routed to binance."
                    : "✕ Declined — nothing was sent."}
                  <button
                    type="button"
                    className="ml-auto border-0 bg-transparent text-ink-mute font-mono text-[0.66rem] underline underline-offset-2 cursor-pointer hover:text-ink"
                    onClick={() => setDecision("pending")}
                  >
                    reset
                  </button>
                </p>
              )}
            </article>
          </div>
        </div>
      </div>
    </section>
  );
}
