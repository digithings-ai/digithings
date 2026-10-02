"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor } from "../../../../../clients/digiquant-tui/src/catalog";
import { EMPTY_READ, STUB_READ, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import { readDeskBlock } from "../read-block";

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
    <div className="grid min-h-0 flex-1 grid-cols-12 grid-rows-12 gap-1 p-1">
      {layout.map((placement) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const view = shown(reads[placement.id]);
        return (
          <section
            key={placement.id}
            aria-label={def.title}
            style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
            className="flex min-h-0 min-w-0 flex-col overflow-hidden border border-hair bg-surface"
          >
            <h2 className="m-0 shrink-0 border-b border-hair px-2 py-1 text-[0.65rem] font-normal text-ink-mute">{def.title}</h2>
            <p className={`m-0 min-h-0 flex-1 overflow-auto whitespace-pre-wrap px-2 py-1 text-[0.7rem] leading-[1.45] ${tone[view.status]}`}>
              {view.lines.join("\n")}
            </p>
            <p className="m-0 shrink-0 truncate border-t border-hair px-2 py-0.5 text-[0.6rem] text-ink-mute">
              {view.asOf ? `as of ${view.asOf}` : def.route}
            </p>
          </section>
        );
      })}
    </div>
  );
}
