"use client";

import { useState } from "react";

/**
 * Collapsible tool-call blocks — the terminal-CLI tool chain (the Claude Code /
 * opencode pattern): each call is a mono line (chevron · tool(args) · status ·
 * timing) that folds its output away. The builder scans the chain, expands the
 * one that matters. Success/error wear the money-adjacent up/down reads; the
 * tool name takes the digichat accent. Reduced motion still toggles (display).
 */
type Call = { tool: string; args: string; ms: string; ok: boolean; out: string[] };

const CALLS: Call[] = [
  {
    tool: "digiquant.backtest",
    args: "trend_xsec · ETH-USD · 8y",
    ms: "412ms",
    ok: true,
    out: [
      "loaded 3,102 bars · fees: binance maker/taker",
      "kelly-capped 0.5× · walk-forward 6 windows",
      "PF 2.31 · win 58% · maxDD −18.4%",
      "tearsheet → vault/trend_xsec.md",
    ],
  },
  {
    tool: "digisearch.query",
    args: '"funding-rate regimes"',
    ms: "88ms",
    ok: true,
    out: ["6 passages · 3 sources", "top: bybit funding methodology (0.91)"],
  },
  {
    tool: "digikey.exchange",
    args: "scope=live:read",
    ms: "—",
    ok: false,
    out: ["✕ token revoked — reissue with `digithings key new`"],
  },
];

function ToolCall({ call, defaultOpen }: { call: Call; defaultOpen: boolean }) {
  const [open, setOpen] = useState(defaultOpen);
  return (
    <div className={`tc${call.ok ? "" : " tc--err"}`}>
      <button
        type="button"
        className="tc-head"
        aria-expanded={open}
        onClick={() => setOpen((v) => !v)}
      >
        <span className="tc-caret" aria-hidden="true" />
        <span className="tc-tool">{call.tool}</span>
        <span className="tc-args">({call.args})</span>
        <span className={`tc-status ${call.ok ? "up" : "down"}`}>{call.ok ? "✓" : "✕"}</span>
        <span className="tc-ms">{call.ms}</span>
      </button>
      {open ? (
        <div className="tc-out">
          {call.out.map((line) => (
            <p key={line} className={line.startsWith("✕") ? "tc-line down" : "tc-line"}>
              {line}
            </p>
          ))}
        </div>
      ) : null}
    </div>
  );
}

export function ChatToolCallReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// tool calls"}</p>
      <h2 className="title">The tool chain, folded.</h2>
      <p className="section-copy">
        Every tool the model runs lands as a collapsible line — chevron, name, arguments, status,
        timing — the way Claude Code and opencode surface a chain. Scan it at a glance, expand the
        one you care about. A failed call reads in the down colour and keeps the fix inline.
      </p>

      <div className="chat-surface mt-[1.3rem] max-w-[760px] flex flex-col gap-[0.7rem] rounded-[12px] border border-term-hair bg-term-bg px-[1.15rem] pt-[1rem] pb-[1.2rem] font-mono">
        <div className="flex gap-[0.55rem] items-baseline justify-start">
          <div className="chat-bubble--user min-w-0 border-0 bg-transparent p-0 font-mono text-[0.84rem] leading-[1.6] text-term-ink">
            backtest trend_xsec on ETH and check the funding regime
          </div>
        </div>
        <div className="flex gap-[0.55rem] items-baseline chat-turn--assistant">
          <span className="shrink-0 font-mono text-[0.86rem] leading-[1.5] text-accent" aria-hidden="true">
            ▸
          </span>
          <div className="chat-stack flex flex-col gap-[0.55rem] min-w-0 flex-1">
            <p className="m-0 mb-[0.55rem] text-ink-soft text-[0.85rem]">running the chain —</p>
            {CALLS.map((c, i) => (
              <ToolCall key={c.tool} call={c} defaultOpen={i === 0} />
            ))}
            <div className="min-w-0 border-0 rounded-none bg-transparent p-0 text-ink-soft text-[0.88rem] leading-[1.6]">
              Backtest passed and the funding notes are attached — but digikey needs a fresh token
              before anything touches live.
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
