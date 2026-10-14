"use client";
/** Every strategy stays mounted. The landing band asks for the compact sheet. */
import { useState } from "react";
import { TabStrip, tabId, tabPanelId } from "@digithings/ui";
import { PUBLISHED_STRATEGIES } from "../published";
import { TearsheetView } from "../tearsheet-view";

const TAB_LABEL = "Strategy";

export function StrategyRailLive({ compact = false }: { compact?: boolean }) {
  const [index, setIndex] = useState(0);

  return (
    <div className="min-w-0">
      <div className="border-b border-hair bg-surface px-3 py-2">
        <p className="m-0 mb-1 font-mono text-[0.68rem] tracking-[0.08em] text-ink-mute uppercase">
          Strategy
        </p>
        <TabStrip
          label={TAB_LABEL}
          variant="pill"
          tabs={PUBLISHED_STRATEGIES.map((item) => ({ id: item.id, label: item.label }))}
          active={index}
          onChange={setIndex}
        />
      </div>
      {PUBLISHED_STRATEGIES.map((item, i) => (
        <div
          key={item.id}
          role="tabpanel"
          id={tabPanelId(TAB_LABEL, item.id)}
          aria-labelledby={tabId(TAB_LABEL, item.id)}
          hidden={i !== index}
        >
          <TearsheetView slug={item.id} embedded compact={compact} />
        </div>
      ))}
    </div>
  );
}
