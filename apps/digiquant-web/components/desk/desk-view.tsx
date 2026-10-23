"use client";

import { BLOCKS, PAGES, layoutFor } from "digiquant-tui/catalog";
import type { ReadResult } from "digiquant-tui/read";
import { DeskFrame } from "./desk-frame";
import { PanelView } from "./panel-view";
import { LiveMarksBlock } from "./blocks/live-marks";
import { PANE_GRID } from "./pages/pane";
import { asOfStatus } from "digiquant-tui/format";
import { staleBanner } from "./app-settings";
import { useAppSettings } from "./app-settings-store";

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

function pageFor(path: string) {
  return PAGES.find((item) => item.path === path) ?? PAGES[0];
}

/** Catalog blocks for one page. The web desk and the terminal frame both paint this grid. */
export function DeskReadout({
  path,
  reads,
  data = {},
}: {
  path: string;
  reads: Record<string, ReadResult | undefined>;
  /** Read payloads by block id. A block with a panel shape and an ok read gets the table/chart toggle. */
  data?: Record<string, unknown>;
}) {
  const page = pageFor(path);
  const layout = layoutFor(page.path);
  const settings = useAppSettings();
  return (
    <div className={PANE_GRID}>
      {layout.map((placement) => {
        const def = BLOCKS[placement.id];
        const read = reads[placement.id];
        const status = read?.status ?? "loading";
        const lines = read?.lines ?? ["loading…"];
        const age = asOfStatus(def.route, read?.asOf, read?.dataAsOf, undefined, settings.staleSessions);
        const banner = staleBanner(age.state, settings.notify);
        const panel = status === "ok" && data[placement.id] !== undefined;
        // `live` is the one pane with no text form. It reads the same official
        // payload, and the table/chart toggle still wins when that payload has a
        // panel shape.
        const live = placement.id === "live";
        return (
          <section
            key={placement.id}
            aria-label={def.title}
            style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
            className="flex min-h-0 min-w-0 flex-col overflow-hidden bg-surface"
          >
            <h2 className="m-0 flex h-7 shrink-0 items-center border-b border-hair px-2.5 font-mono text-[0.6875rem] font-normal tracking-[0.04em] text-ink-mute">{def.title}</h2>
            {live ? (
              <div
                role="region"
                aria-label={`${def.title} body`}
                tabIndex={0}
                className={`desk-pane-body flex min-h-0 flex-1 flex-col overflow-auto px-2.5 py-1.5 font-mono text-[0.75rem] leading-[1.45] tabular-nums ${tone[status]}`}
              >
                {panel ? (
                  <PanelView id={placement.id} title={def.title} data={data[placement.id]}>
                    <LiveMarksBlock read={read} data={data[placement.id]} />
                  </PanelView>
                ) : (
                  <LiveMarksBlock read={read} data={data[placement.id]} />
                )}
              </div>
            ) : status === "ok" && data[placement.id] !== undefined ? (
              <div
                role="region"
                aria-label={`${def.title} body`}
                tabIndex={0}
                className={`desk-pane-body flex min-h-0 flex-1 flex-col overflow-auto px-2.5 py-1.5 font-mono text-[0.75rem] leading-[1.45] tabular-nums ${tone[status]}`}
              >
                <PanelView id={placement.id} title={def.title} data={data[placement.id]}>
                  <p className="m-0 whitespace-pre-wrap">{lines.slice(0, 14).join("\n")}</p>
                </PanelView>
              </div>
            ) : (
              <p
                tabIndex={0}
                className={`desk-pane-body m-0 min-h-0 flex-1 overflow-auto whitespace-pre-wrap px-2.5 py-1.5 font-mono text-[0.75rem] leading-[1.45] tabular-nums ${tone[status]}`}
              >
                {lines.slice(0, 14).join("\n")}
              </p>
            )}
            <p className="m-0 flex h-7 shrink-0 items-center truncate border-t border-hair px-2.5 font-mono text-[0.6875rem] tracking-[0.04em] text-ink-mute tabular-nums">
              {age.label}
              {banner ? (
                <span role="status" data-stale-banner=""> · {banner}</span>
              ) : null}
            </p>
          </section>
        );
      })}
    </div>
  );
}

/** The catalog pages inside the web desk frame. */
export function DeskView({ path, reads }: { path: string; reads: Record<string, ReadResult | undefined> }) {
  const page = pageFor(path);
  return (
    <DeskFrame current={page.path}>
      <DeskReadout path={path} reads={reads} />
    </DeskFrame>
  );
}
