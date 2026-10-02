import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockDef } from "../catalog";
import { COLS, ROWS, type Placement } from "../grid";
import { DASH, EMPTY_READ, readBlock, type ReadResult } from "../read";

/**
 * Pipeline page for the terminal. One block per official read.
 * Run health is not drawn: a missing table stays the nulls in that read.
 *
 * pl-narrative       GET /pipeline/runs/latest/narrative
 * pl-artifacts       GET /pipeline/runs/latest/artifacts
 * pl-canvas          GET /pipeline/runs/latest/graph
 * pl-node-document   GET /pipeline/runs/latest/nodes/selected/document
 * pl-call-trace      GET /pipeline/runs/latest/trace
 */

const BG = "#14120f";
const INK = "#e7e1d6";
const DIM = "#8a8175";
const LINE = "#3a342c";
const OK = "#7d9a78";
const BAD = "#c47a6a";

const PIPELINE_IDS = ["pl-narrative", "pl-artifacts", "pl-canvas", "pl-node-document", "pl-call-trace"] as const;
type PipelineId = (typeof PIPELINE_IDS)[number];

const DEFAULT_API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

function isPipelineId(id: string): id is PipelineId {
  return (PIPELINE_IDS as readonly string[]).includes(id);
}

function tone(status: ReadResult["status"] | "loading"): string {
  if (status === "ok") return INK;
  if (status === "empty" || status === "loading") return DIM;
  return BAD;
}

function border(status: ReadResult["status"] | "loading"): string {
  if (status === "ok") return OK;
  if (status === "empty" || status === "loading") return LINE;
  return BAD;
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

function PipelineBlock({ read }: { read: ReadResult | undefined }) {
  const status = read?.status ?? "loading";
  return <text fg={tone(status)}>{linesOf(read).join("\n")}</text>;
}

/** Terminal pipeline. Not mounted by the spine. */
export function PipelinePage({ api = DEFAULT_API }: { api?: string }) {
  const [reads, setReads] = useState<Partial<Record<PipelineId, ReadResult>>>({});
  const blocks = pipelinePlacements();

  useEffect(() => {
    const ac = new AbortController();
    let cancel = false;
    setReads({});
    for (const { id, def } of pipelinePlacements()) {
      void readBlock(api, def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api]);

  return (
    <box width="100%" height="100%" position="relative" backgroundColor={BG}>
      {blocks.map(({ id, def, placement }) => {
        const read = reads[id];
        const status = read?.status ?? "loading";
        return (
          <box
            key={id}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            border
            borderColor={border(status)}
            title={def.title}
            titleColor={DIM}
            bottomTitle={read?.asOf ? `as of ${read.asOf}` : def.route}
            overflow="hidden"
            paddingLeft={1}
            paddingRight={1}
          >
            <PipelineBlock read={read} />
          </box>
        );
      })}
    </box>
  );
}
