"use client";

import { useState } from "react";

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

      <div className="chat-surface">
        {/* Widget 1 — backtest result card */}
        <div className="chat-turn chat-turn--assistant">
          <span className="chat-mark" aria-hidden="true">
            ▸
          </span>
          <div className="chat-bubble chat-bubble--bare">
            <article className="widget widget-result">
              <header className="widget-head">
                <div>
                  <p className="widget-eyebrow">backtest complete</p>
                  <h4 className="widget-title">trend_xsec · ETH-USD · 8y</h4>
                </div>
                <span className="widget-badge ok">passed</span>
              </header>
              <div className="widget-metrics">
                {METRICS.map((m) => (
                  <div key={m.k} className="widget-metric">
                    <span className="widget-metric-k">{m.k}</span>
                    <span className={`widget-metric-v${m.tone === "down" ? " down" : ""}`}>
                      {m.v}
                    </span>
                  </div>
                ))}
              </div>
              <footer className="widget-actions">
                <button type="button" className="widget-btn primary">
                  View tearsheet
                </button>
                <button type="button" className="widget-btn ghost">
                  Save to vault
                </button>
              </footer>
            </article>
          </div>
        </div>

        {/* Widget 2 — human-approval gate */}
        <div className="chat-turn chat-turn--assistant">
          <span className="chat-mark" aria-hidden="true">
            ▸
          </span>
          <div className="chat-bubble chat-bubble--bare">
            <article className={`widget widget-approve state-${decision}`}>
              <header className="widget-head">
                <div>
                  <p className="widget-eyebrow">requires approval</p>
                  <h4 className="widget-title">Route live order → binance</h4>
                </div>
                <span className="widget-lock" aria-hidden="true">
                  <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
                    <rect x="5" y="11" width="14" height="9" rx="2" />
                    <path d="M8 11V8a4 4 0 0 1 8 0v3" />
                  </svg>
                </span>
              </header>
              <dl className="widget-order">
                <div>
                  <dt>side</dt>
                  <dd className="up">buy</dd>
                </div>
                <div>
                  <dt>size</dt>
                  <dd>0.40 BTC</dd>
                </div>
                <div>
                  <dt>limit</dt>
                  <dd>63,410</dd>
                </div>
              </dl>
              {decision === "pending" ? (
                <footer className="widget-actions">
                  <button
                    type="button"
                    className="widget-btn primary"
                    onClick={() => setDecision("approved")}
                  >
                    Approve
                  </button>
                  <button
                    type="button"
                    className="widget-btn danger"
                    onClick={() => setDecision("declined")}
                  >
                    Decline
                  </button>
                </footer>
              ) : (
                <p className={`widget-resolved ${decision}`}>
                  {decision === "approved"
                    ? "✓ Approved — order routed to binance."
                    : "✕ Declined — nothing was sent."}
                  <button
                    type="button"
                    className="widget-undo"
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
