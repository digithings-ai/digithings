"use client";
/** Tearsheets band: one strategy at a time, the same sheet as the strategy page. */
import { useState } from "react";
import { TabStrip, tabId, tabPanelId } from "@digithings/ui";
import { PUBLISHED_STRATEGIES } from "../published";
import { TearsheetView } from "../tearsheet-view";

const TAB_LABEL = "Strategy tearsheet";

export function StrategyRailLive() {
  const [index, setIndex] = useState(0);
  const strategy = PUBLISHED_STRATEGIES[index] ?? PUBLISHED_STRATEGIES[0];
  if (!strategy) return null;

  return (
    <div className="grid min-w-0 gap-3">
      <TabStrip
        label={TAB_LABEL}
        variant="underline"
        sharedPanel
        tabs={PUBLISHED_STRATEGIES.map((item) => ({ id: item.id, label: item.label }))}
        active={index}
        onChange={setIndex}
      />
      <div
        role="tabpanel"
        id={tabPanelId(TAB_LABEL, strategy.id)}
        aria-labelledby={tabId(TAB_LABEL, strategy.id)}
      >
        <TearsheetView slug={strategy.id} embedded />
      </div>
    </div>
  );
}
