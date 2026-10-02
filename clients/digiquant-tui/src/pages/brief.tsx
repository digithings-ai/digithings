import { useEffect, useState } from "react";
import { BLOCKS, layoutFor } from "../catalog";
import { COLS, ROWS } from "../grid";
import { EMPTY_READ, STUB_READ, readBlock, type ReadResult } from "../read";

/** Brief desk. One block per official read. A down API or a stub stays a sentence. */
const PATH = "/brief";
const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");

const BG = "#14120f";
const INK = "#e7e1d6";
const DIM = "#8a8175";
const LINE = "#3a342c";
const BAD = "#c47a6a";
const OK = "#7d9a78";

const STUB_MARKS = ["99.909", "204.04", "legacy_estimate"];

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

const tone = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return INK;
  if (status === "empty" || status === "loading") return DIM;
  return BAD;
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
      void readBlock(API, def.route, def.kind, ac.signal).then((result) => {
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
    <box width="100%" height="100%" position="relative" overflow="hidden" backgroundColor={BG}>
      {layout.map((placement) => {
        const def = BLOCKS[placement.id];
        if (!def) return null;
        const view = shown(reads[placement.id]);
        return (
          <box
            key={placement.id}
            position="absolute"
            left={share(placement.x - 1, COLS)}
            top={share(placement.y - 1, ROWS)}
            width={share(placement.w, COLS)}
            height={share(placement.h, ROWS)}
            border
            borderColor={view.status === "ok" ? OK : view.status === "empty" || view.status === "loading" ? LINE : BAD}
            title={def.title}
            titleColor={DIM}
            bottomTitle={view.asOf ? `as of ${view.asOf}` : def.route}
            overflow="hidden"
            paddingLeft={1}
            paddingRight={1}
          >
            <text fg={tone(view.status)}>{view.lines.join("\n")}</text>
          </box>
        );
      })}
    </box>
  );
}
