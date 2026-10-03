"use client";

import { Band } from "../_chrome/Band";
import { ScriptedDigichatSession } from "@/components/chat/scripted-session";

export function ChatBand() {
  return (
    <Band
      id="chat"
      fill
      title="From a chat to a tested strategy"
      takeaway="digichat takes a trend-following idea through the indicators, the strategy components, a viability check, an optimization pass, and the backtest, and posts each result in the thread. The same sidebar holds a research note, a trade journal, and the daily digest."
    >
      <div className="mx-auto flex w-full max-w-[64rem] flex-1 flex-col">
        <ScriptedDigichatSession />
      </div>
    </Band>
  );
}
