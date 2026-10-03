"use client";

import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockDef } from "../../../../../clients/digiquant-tui/src/catalog";
import { DASH, EMPTY_READ, type ReadResult } from "../../../../../clients/digiquant-tui/src/read";
import type { Placement } from "../../../../../clients/digiquant-tui/src/grid";
import { readDeskBlock } from "../read-block";
import { DeskPane, PANE_GRID, usePaneFocus } from "./pane";

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

/** Desk pipeline. Not mounted by the frame. */
export function PipelinePage() {
  const [reads, setReads] = useState<Partial<Record<PipelineId, ReadResult>>>({});
  const blocks = pipelinePlacements();
  const panes = usePaneFocus(blocks.map((block) => block.id));

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
    <div className={PANE_GRID}>
      {blocks.map(({ id, def, placement }) => {
        const read = reads[id];
        const status = read?.status ?? "loading";
        return (
          <div
            key={id}
            data-block={id}
            className="flex min-h-0 min-w-0"
            style={{ gridColumn: `${placement.x} / span ${placement.w}`, gridRow: `${placement.y} / span ${placement.h}` }}
          >
            <DeskPane
              title={def.title}
              route={def.route}
              asOf={read?.asOf ?? null}
              lines={linesOf(read)}
              tone={tone[status]}
              focused={panes.focus === id}
              onFocus={() => panes.focusAt(id)}
              onNext={panes.next}
            />
          </div>
        );
      })}
    </div>
  );
}
