"use client";

import { useEffect, useRef, useState } from "react";
import { ChatPlayback } from "@digithings/ui";
import { Band } from "../_chrome/Band";
import {
  STRATEGY_BADGE,
  STRATEGY_HEADER,
  STRATEGY_SCRIPT,
  STRATEGY_STEPS,
} from "../_strategy-script";

type StepState = "idle" | "running" | "done";

/** Reads the chat's own rendered rows (the kit part exposes no step callback) and
 *  maps each ledger step to idle, running or done. Server render and no-JS start
 *  as all done, matching the full static transcript. */
function useStepStates(ref: React.RefObject<HTMLDivElement | null>): StepState[] {
  const [states, setStates] = useState<StepState[]>(() => STRATEGY_STEPS.map(() => "done"));
  useEffect(() => {
    const root = ref.current;
    if (!root) return;
    const frame = root.querySelector<HTMLElement>('[data-slot="chat-playback"]');
    if (!frame) return;
    const read = () => {
      const mode = frame.dataset.mode;
      const rows = Array.from(frame.querySelectorAll<HTMLElement>(".tc"));
      const next = STRATEGY_STEPS.map((step): StepState => {
        if (mode === "static" || mode === "done") return "done";
        const row = rows.find((r) => r.textContent?.includes(step.tool));
        if (!row) return "idle";
        return row.querySelector(".tc-run") ? "running" : "done";
      });
      setStates((prev) => (prev.every((v, i) => v === next[i]) ? prev : next));
    };
    read();
    const mo = new MutationObserver(read);
    mo.observe(frame, { subtree: true, childList: true, attributes: true, attributeFilter: ["data-mode", "class"] });
    return () => mo.disconnect();
  }, [ref]);
  return states;
}

const CELL =
  "relative flex min-w-0 flex-1 flex-col gap-[0.15rem] border-e border-hair px-3 py-2 font-mono transition-colors duration-300 last:border-e-0 motion-reduce:transition-none";

/** Step ledger above the chat: one cell per real tool call, in order. A cell lights
 *  (accent bar + ink text) when its call starts and settles when it returns. */
function StepLedger({ states }: { states: StepState[] }) {
  return (
    <ol
      aria-label="Tool calls in this script"
      className="m-0 flex list-none border border-hair p-0"
    >
      {STRATEGY_STEPS.map((step, i) => {
        const st = states[i] ?? "done";
        const lit = st === "running";
        return (
          <li key={step.tool} className={`${CELL} ${lit ? "bg-surface-2" : ""}`} data-state={st}>
            <span
              aria-hidden="true"
              className={`absolute inset-y-0 start-0 w-[2px] origin-top bg-accent transition-[opacity,transform] duration-300 motion-reduce:transition-none ${
                lit ? "scale-y-100 opacity-100" : st === "done" ? "scale-y-100 opacity-40" : "scale-y-0 opacity-0"
              }`}
            />
            <span className="text-[0.62rem] text-ink-mute">[{String(i + 1).padStart(2, "0")}]</span>
            <span className={`text-[0.78rem] ${st === "idle" ? "text-ink-mute" : "text-ink"}`}>{step.label}</span>
            <span className="text-[0.62rem] text-ink-mute">
              {step.scope === "read" ? "read scope" : "full scope"}
              {st === "done" ? " ✓" : lit ? " …" : ""}
            </span>
          </li>
        );
      })}
    </ol>
  );
}

export function ChatBand() {
  const ref = useRef<HTMLDivElement>(null);
  const states = useStepStates(ref);
  return (
    <Band
      id="chat"
      fill
      status="story · in development"
      title="From a chat to a tested strategy"
      takeaway="An agent takes an idea from digichat, runs it through the backtester and optimizer, and reports each result for you to inspect. Scripted, not live: the builder lives in the dashboard."
    >
      <div ref={ref} className="mx-auto flex w-full max-w-[64rem] flex-1 flex-col gap-3">
        <div
          aria-label="digichat container"
          className="overflow-hidden border border-hair bg-surface"
        >
          <div className="flex items-center justify-between gap-3 border-b border-hair bg-surface-2 px-4 py-2">
            <span className="flex items-center gap-2 font-mono text-[0.68rem] text-ink-mute">
              <span aria-hidden="true" className="flex gap-1.5">
                <span className="inline-block size-2.5 rounded-full bg-hair" />
                <span className="inline-block size-2.5 rounded-full bg-hair" />
                <span className="inline-block size-2.5 rounded-full bg-accent" />
              </span>
              digichat · strategy thread
            </span>
            <span className="font-mono text-[0.68rem] text-ink-mute">read scope · scripted replay</span>
          </div>
          <div className="grid md:grid-cols-[12rem_minmax(0,1fr)]">
            <div aria-hidden="true" className="hidden border-e border-hair p-3 font-mono text-[0.66rem] leading-[1.7] text-ink-mute md:block">
              <p className="m-0 text-ink">threads</p>
              <p className="m-0 text-ink-soft">▸ vela breakout v3</p>
              <p className="m-0">mean-revert spy</p>
              <p className="m-0">edge report q3</p>
            </div>
            <ChatPlayback
              script={STRATEGY_SCRIPT}
              badge={STRATEGY_BADGE}
              header={STRATEGY_HEADER}
              ariaLabel="Scripted strategy-building story"
              className="min-h-0 flex-1 [&>div.overflow-y-auto]:h-[min(34rem,calc(100svh-22rem))]"
            />
          </div>
        </div>
        <StepLedger states={states} />
      </div>
    </Band>
  );
}
