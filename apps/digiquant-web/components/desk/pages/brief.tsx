"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor } from "../../../../../clients/digiquant-tui/src/catalog";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import { readDeskBlock } from "../read-block";
import { DeskPane, PANE_GRID, usePaneFocus } from "./pane";

/** Brief desk. One block per official read. A down API or a stub stays a sentence. */
const PATH = "/brief";

const STUB_MARKS = ["99.909", "204.04", "legacy_estimate"];

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

type Shown = { status: ReadResult["status"] | "loading"; lines: string[]; asOf: string | null };

function shown(read: ReadResult | undefined): Shown {
  if (!read) return { status: "loading", lines: ["loading…"], asOf: null };
  if (read.status === "stub" || read.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", lines: [STUB_READ], asOf: null };
  }
  if (read.lines.length === 0) return { status: read.status === "ok" ? "empty" : read.status, lines: [EMPTY_READ], asOf: null };
  return { status: read.status, lines: read.lines.slice(0, 14), asOf: read.asOf };
}

export function BriefPage() {
  const [reads, setReads] = useState<Record<string, ReadResult>>({});
  const layout = layoutFor(PATH);
  const panes = usePaneFocus(layout.map((placement) => placement.id));

  useEffect(() => {
    const placements = layoutFor(PATH);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void readDeskBlock(def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, []);

  return (
    <div className={PANE_GRID}>
      {layout.map((placement) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const view = shown(reads[placement.id]);
        return (
          <div
            key={placement.id}
            className="min-h-0 min-w-0"
            style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
          >
            <DeskPane
              title={def.title}
              route={def.route}
              asOf={view.asOf}
              lines={view.lines}
              tone={tone[view.status]}
              focused={panes.focus === placement.id}
              onFocus={() => panes.focusAt(placement.id)}
              onNext={panes.next}
            />
          </div>
        );
      })}
    </div>
  );
}
