"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor } from "../../../../../clients/digiquant-tui/src/catalog";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import { briefBlocks } from "../../../../../clients/digiquant-tui/src/pages/brief-format";
import { shapeLines, type PaneBody } from "../../../../../clients/digiquant-tui/src/pages/shape";
import { readOfficial, type OfficialRead } from "../read-block";
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

function paint(id: string, read: OfficialRead | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: briefBlocks(id, read.data, read.result), asOf: read.result.asOf };
}

export function BriefPage() {
  const [reads, setReads] = useState<Record<string, OfficialRead>>({});
  const layout = layoutFor(PATH);
  const panes = usePaneFocus(layout.map((placement) => placement.id));

  useEffect(() => {
    const placements = layoutFor(PATH);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void readOfficial(def.route, def.kind, ac.signal).then((result) => {
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
        const view = paint(placement.id, reads[placement.id]);
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
              blocks={view.blocks}
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
