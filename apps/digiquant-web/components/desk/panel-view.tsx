"use client";

import { useSyncExternalStore, type ReactNode } from "react";
import { Button } from "@digithings/ui/ui";
import {
  CHART_LABEL,
  chartFor,
  chartPoints,
  panelData,
  type ChartType,
  type PanelMode,
} from "../../../../clients/digiquant-tui/src/pages/panel-shape";
import { PanelChart } from "./panel-chart";

type Pick = { mode?: PanelMode; chart?: ChartType };

const KEY = "dq.panel.";
const PANE_META = "font-mono text-[0.6875rem] font-normal tracking-[0.04em]";

/** This tab's picks. Storage can refuse a write; the pick still holds until reload. */
const memory = new Map<string, string>();
const listeners = new Set<() => void>();

function subscribe(listener: () => void): () => void {
  listeners.add(listener);
  window.addEventListener("storage", listener);
  return () => {
    listeners.delete(listener);
    window.removeEventListener("storage", listener);
  };
}

function readRaw(id: string): string {
  const held = memory.get(id);
  if (held !== undefined) return held;
  try {
    return window.localStorage.getItem(KEY + id) ?? "";
  } catch {
    return "";
  }
}

function parsePick(raw: string): Pick {
  try {
    const parsed: unknown = raw ? JSON.parse(raw) : null;
    return parsed && typeof parsed === "object" ? (parsed as Pick) : {};
  } catch {
    return {};
  }
}

function savePick(id: string, pick: Pick) {
  const raw = JSON.stringify(pick);
  memory.set(id, raw);
  try {
    window.localStorage.setItem(KEY + id, raw);
  } catch {
    // Private mode or a full store: the in-memory pick is enough.
  }
  for (const listener of listeners) listener();
}

function Toggle({ on, onClick, children }: { on: boolean; onClick: () => void; children: ReactNode }) {
  return (
    <Button
      type="button"
      variant="ghost"
      size="xs"
      aria-pressed={on}
      className={`h-6 rounded-none px-1.5 ${PANE_META} ${on ? "text-ink" : "text-ink-mute"}`}
      onClick={onClick}
    >
      {children}
    </Button>
  );
}

/** One pane body with a table/chart toggle and a chart-type picker.
 *  A block with no panel shape, or too few points, shows its table with no controls. */
export function PanelView({ id, title, data, children }: { id: string; title: string; data: unknown; children: ReactNode }) {
  const panel = panelData(id, data);
  const raw = useSyncExternalStore(subscribe, () => readRaw(id), () => "");
  const pick = parsePick(raw);

  if (!panel) return <>{children}</>;

  const mode = pick.mode === "table" || pick.mode === "chart" ? pick.mode : panel.spec.mode;
  const chart = chartFor(panel, pick.chart);
  const update = (next: Pick) => {
    savePick(id, { ...pick, ...next });
  };
  const drawn = chartPoints(panel);

  return (
    <div data-panel={id} data-mode={mode} className="flex min-h-0 flex-1 flex-col gap-1">
      <div role="toolbar" aria-label={`${title} view`} className="-mx-1 flex shrink-0 flex-wrap items-center gap-x-2">
        <div role="group" aria-label="View" className="flex">
          <Toggle on={mode === "table"} onClick={() => update({ mode: "table" })}>
            Table
          </Toggle>
          <Toggle on={mode === "chart"} onClick={() => update({ mode: "chart" })}>
            Chart
          </Toggle>
        </div>
        {mode === "chart" && panel.charts.length > 1 ? (
          <div role="group" aria-label="Chart type" className="flex border-l border-hair pl-1">
            {panel.charts.map((type) => (
              <Toggle key={type} on={chart === type} onClick={() => update({ chart: type })}>
                {CHART_LABEL[type]}
              </Toggle>
            ))}
          </div>
        ) : null}
      </div>
      {mode === "table" ? (
        children
      ) : (
        <figure className="m-0 flex min-h-0 flex-1 flex-col">
          <div className="min-h-0 flex-1">
            <PanelChart shape={panel.spec.shape} type={chart} points={drawn.points} unit={panel.spec.unit} label={`${title}, ${CHART_LABEL[chart]} chart`} />
          </div>
          {drawn.hidden > 0 ? (
            <figcaption className="text-ink-mute">{`${drawn.hidden} more in the table.`}</figcaption>
          ) : null}
        </figure>
      )}
    </div>
  );
}
