"use client";

import { Band } from "../_chrome/Band";
import { ScriptedDigichatSession } from "@/components/chat/scripted-session";

export function ChatBand() {
  return (
    <Band
      id="chat"
      fill
      status="scripted · not a live session"
      title="From a chat to a tested strategy"
      takeaway="An agent takes an idea from digichat, runs it through the backtester and optimizer, and reports each result for you to inspect. Scripted, not live: the builder lives in the dashboard."
    >
      <div className="mx-auto flex w-full max-w-[64rem] flex-1 flex-col">
        <ScriptedDigichatSession />
      </div>
    </Band>
  );
}
