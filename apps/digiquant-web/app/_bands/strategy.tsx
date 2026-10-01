"use client";

import { useEffect, useRef, useState } from "react";
import { ChatPlayback } from "@digithings/ui";
import { LocalLuxalgoWorkflow } from "@/components/luxalgo/local-luxalgo-workflow";
import { Band } from "../_chrome/Band";
import { ChartFramePlaceholder, DashboardFlowPlaceholder } from "../_placeholders";
import {
  STRATEGY_BADGE,
  STRATEGY_HEADER,
  STRATEGY_LEDGER,
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
  "relative flex min-w-0 flex-1 flex-col gap-[0.15rem] border-hair px-3 py-2 font-mono transition-colors duration-300 motion-reduce:transition-none max-md:border-e last:max-md:border-e-0 md:flex-1 md:justify-center md:border-b md:last:border-b-0";

/** Left-margin step ledger: one cell per real tool call, in order. A cell lights
 *  (accent bar + ink text) when its call starts and settles when it returns. */
function StepLedger({ states }: { states: StepState[] }) {
  return (
    <ol
      aria-label="Tool calls in this script"
      className="m-0 flex list-none border border-hair bg-surface p-0 md:flex-col md:self-stretch"
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

function StatusLedger() {
  return (
    <dl className="m-0 border border-hair font-mono text-[0.72rem] leading-[1.55]">
      {STRATEGY_LEDGER.map((row) => (
        <div key={row.key} className="grid border-b border-hair last:border-b-0 sm:grid-cols-[12rem_minmax(0,1fr)]">
          <dt className="px-3 pb-0 pt-2 text-ink-mute sm:border-e sm:border-hair sm:pb-2">[ {row.key} ]</dt>
          <dd className="m-0 px-3 pb-2 pt-0 font-sans text-[0.8125rem] text-ink-soft sm:pt-2">{row.value}</dd>
        </div>
      ))}
    </dl>
  );
}

export function StrategyBand() {
  const ref = useRef<HTMLDivElement>(null);
  const states = useStepStates(ref);
  return (
    <Band
      id="workflow"
      status="story · in development"
      title="From a chat to a Nautilus backtest"
      takeaway="How a strategy gets built: describe it in digichat, backtest it on Nautilus, inspect the result, hand it off. The builder lives in the dashboard. This is the story of it, and it is not live yet."
    >
      <div ref={ref} className="flex flex-col gap-4">
        <DashboardFlowPlaceholder />
        <div className="grid gap-4 md:grid-cols-[8.5rem_minmax(0,1fr)]">
          <StepLedger states={states} />
          <ChatPlayback
            script={STRATEGY_SCRIPT}
            badge={STRATEGY_BADGE}
            header={STRATEGY_HEADER}
            ariaLabel="Scripted strategy-building story"
          />
        </div>
        <StatusLedger />
        <LocalLuxalgoWorkflow />
        <ChartFramePlaceholder />
      </div>
    </Band>
  );
}
