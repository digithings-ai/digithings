import { useEffect, useState } from "react";
import { BLOCKS, layoutFor, type BlockKind } from "../catalog";
import { COLS, ROWS } from "../grid";
import { EMPTY_READ, STUB_READ, presentResponse, type ReadResult } from "../read";
import { DANGER, INK, MUTE } from "../theme";
import { pipelineBody } from "./pipeline-format";
import { PaneFrame, useFocusedPane } from "./pane";
import { shapeLines, type PaneBody } from "./shape";

/** Pipeline desk. One block per official read. A down API or a stub stays a sentence. */
const PATH = "/pipeline";
const DEFAULT_API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

const STUB_MARKS = ["99.909", "204.04", "legacy_estimate"];

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

const tone = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return INK;
  if (status === "empty" || status === "loading") return MUTE;
  return DANGER;
};

type Loaded = { result: ReadResult; data: unknown };

async function loadPipeline(api: string, route: string, kind: BlockKind, signal?: AbortSignal): Promise<Loaded> {
  let res: Response;
  try {
    res = await fetch(`${api}${route}`, { signal });
  } catch {
    if (signal?.aborted) return { result: { status: "error", lines: [], asOf: null }, data: null };
    return { result: { status: "error", lines: [`${route}: the official API could not be reached.`], asOf: null }, data: null };
  }
  let body: unknown = null;
  try {
    body = await res.json();
  } catch {
    body = null;
  }
  const result = presentResponse(route, res.status, body, kind);
  if (result.status === "error" || result.status === "stub") return { result, data: null };
  const data = body && typeof body === "object" && "data" in body ? (body as { data: unknown }).data : null;
  return { result, data };
}

function paint(id: string, read: Loaded | undefined): { status: ReadResult["status"] | "loading"; blocks: PaneBody; asOf: string | null } {
  if (!read) return { status: "loading", blocks: shapeLines(["loading…"]), asOf: null };
  if (read.result.status === "stub" || read.result.lines.some((line) => STUB_MARKS.some((mark) => line.includes(mark)))) {
    return { status: "stub", blocks: shapeLines([STUB_READ]), asOf: null };
  }
  if (read.result.lines.length === 0 && read.result.status !== "ok") {
    return { status: read.result.status, blocks: shapeLines([EMPTY_READ]), asOf: null };
  }
  return { status: read.result.status, blocks: pipelineBody(id, read.data, read.result), asOf: read.result.asOf };
}

/** Terminal pipeline. Run health, narrative, artifacts, nodes, the node document, and the call trace. */
export function PipelinePage({ api = DEFAULT_API }: { api?: string }) {
  const [reads, setReads] = useState<Record<string, Loaded>>({});
  const layout = layoutFor(PATH);
  const [focus, setFocus] = useFocusedPane(layout.length);

  useEffect(() => {
    const placements = layoutFor(PATH);
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      if (!def) continue;
      void loadPipeline(api, def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [api]);

  return (
    <box width="100%" height="100%" position="relative" overflow="hidden">
      {layout.map((placement, index) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const view = paint(placement.id, reads[placement.id]);
        return (
          <box
            key={placement.id}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            onMouseDown={() => setFocus(index)}
          >
            <PaneFrame
              title={def.title}
              status={view.asOf ? `as of ${view.asOf}` : def.route}
              focused={index === focus}
              blocks={view.blocks}
              ink={tone(view.status)}
            />
          </box>
        );
      })}
    </box>
  );
}
