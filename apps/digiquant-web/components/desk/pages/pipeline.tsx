"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockDef } from "../../../../../clients/digiquant-tui/src/catalog";
import { DASH, EMPTY_READ, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import type { Placement } from "../../../../../clients/digiquant-tui/src/grid";
import { readDeskBlock } from "../read-block";

/**
 * Pipeline page for the desk. One block per official read. Same reads as the terminal.
 * Run health is not drawn: a missing table stays the nulls in that read.
 *
 * pl-narrative       GET /pipeline/runs/latest/narrative
 * pl-artifacts       GET /pipeline/runs/latest/artifacts
 * pl-canvas          GET /pipeline/runs/latest/graph
 * pl-node-document   GET /pipeline/runs/latest/nodes/selected/document
 * pl-call-trace      GET /pipeline/runs/latest/trace
 */

const PIPELINE_IDS = ["pl-narrative", "pl-artifacts", "pl-canvas", "pl-node-document", "pl-call-trace"] as const;
type PipelineId = (typeof PIPELINE_IDS)[number];

const tone: Record<ReadResult["status"] | "loading", string> = {
  ok: "text-ink",
  empty: "text-ink-mute",
  loading: "text-ink-mute",
  stub: "text-ink-soft",
  error: "text-ink-soft",
};

function isPipelineId(id: string): id is PipelineId {
  return (PIPELINE_IDS as readonly string[]).includes(id);
}

function linesOf(read: ReadResult | undefined): string[] {
  if (!read) return ["loading…"];
  if (read.lines.length > 0) return read.lines;
  return read.status === "empty" ? [EMPTY_READ] : [DASH];
}

function pipelinePlacements(): { id: PipelineId; def: BlockDef; placement: Placement }[] {
  const out: { id: PipelineId; def: BlockDef; placement: Placement }[] = [];
  for (const placement of layoutFor("/pipeline")) {
    if (!isPipelineId(placement.id)) continue;
    const def = BLOCKS[placement.id];
    if (!def) continue;
    out.push({ id: placement.id, def, placement });
  }
  return out;
}

function PipelineBlock({ def, read }: { def: BlockDef; read: ReadResult | undefined }) {
  const status = read?.status ?? "loading";
  const lines = linesOf(read);
  return (
    <section aria-label={def.title} data-route={def.route} className="flex min-h-0 min-w-0 flex-1 flex-col overflow-hidden border border-hair bg-surface">
      <h2 className="m-0 shrink-0 border-b border-hair px-2 py-1 text-[0.65rem] font-normal text-ink-mute">{def.title}</h2>
      <p className={`m-0 min-h-0 flex-1 overflow-auto whitespace-pre-wrap px-2 py-1 text-[0.7rem] leading-[1.45] ${tone[status]}`}>
        {lines.join("\n")}
      </p>
      <p className="m-0 shrink-0 truncate border-t border-hair px-2 py-0.5 text-[0.6rem] text-ink-mute">
        {read?.asOf ? `as of ${read.asOf}` : def.route}
      </p>
    </section>
  );
}

/** Desk pipeline. Not mounted by the frame. */
export function PipelinePage() {
  const [reads, setReads] = useState<Partial<Record<PipelineId, ReadResult>>>({});
  const blocks = pipelinePlacements();

  useEffect(() => {
    const ac = new AbortController();
    let cancel = false;
    for (const { id, def } of pipelinePlacements()) {
      void readDeskBlock(def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, []);

  return (
    <div className="grid min-h-0 flex-1 grid-cols-12 grid-rows-12 gap-1 p-1">
      {blocks.map(({ id, def, placement }) => (
        <div
          key={id}
          data-block={id}
          className="flex min-h-0 min-w-0"
          style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
        >
          <PipelineBlock def={def} read={reads[id]} />
        </div>
      ))}
    </div>
  );
}
