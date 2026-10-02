import { writeFile } from "node:fs/promises";
import { useKeyboard, useRenderer } from "@opentui/react";
import { useEffect, useRef, useState } from "react";
import { BLOCKS, PAGES, pageByPath, layoutFor } from "./catalog";
import { COLS, ROWS, nudge, type Layout } from "./grid";
import { readBlock, type ReadResult } from "./read";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");
const STATUS = process.env.DQ_TUI_STATUS;

const BG = "#14120f";
const INK = "#e7e1d6";
const DIM = "#8a8175";
const LINE = "#3a342c";
const GOLD = "#d4b483";
const BAD = "#c47a6a";
const OK = "#7d9a78";

type Key = { name?: string; shift?: boolean; sequence?: string };

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

const tone = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return INK;
  if (status === "empty") return DIM;
  if (status === "loading") return DIM;
  return BAD;
};

export function App() {
  const renderer = useRenderer();
  const arg = process.argv.find((a) => a.startsWith("/") && pageByPath(a));
  const [pageIndex, setPageIndex] = useState(() => Math.max(0, PAGES.findIndex((p) => p.path === arg)));
  const [layout, setLayout] = useState<Layout>(() => layoutFor(PAGES[Math.max(0, PAGES.findIndex((p) => p.path === arg))].path));
  const [focus, setFocus] = useState(-1);
  const [mode, setMode] = useState<"desk" | "goto">("desk");
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [reads, setReads] = useState<Record<string, ReadResult>>({});

  const pageRef = useRef(pageIndex);
  const layoutRef = useRef(layout);
  const focusRef = useRef(focus);
  const modeRef = useRef(mode);
  pageRef.current = pageIndex;
  layoutRef.current = layout;
  focusRef.current = focus;
  modeRef.current = mode;

  const page = PAGES[pageIndex];

  useEffect(() => {
    const placements = layoutFor(page.path);
    setLayout(placements);
    setFocus(-1);
    setReads({});
    const ac = new AbortController();
    let cancel = false;
    for (const placement of placements) {
      const def = BLOCKS[placement.id];
      void readBlock(API, def.route, def.kind, ac.signal).then((result) => {
        if (cancel) return;
        setReads((prev) => ({ ...prev, [placement.id]: result }));
      });
    }
    return () => {
      cancel = true;
      ac.abort();
    };
  }, [page.path]);

  useEffect(() => {
    if (!STATUS) return;
    if (layout.some((p) => !reads[p.id])) return;
    const payload = {
      path: page.path,
      blocks: layout.map((p) => ({
        id: p.id,
        route: BLOCKS[p.id].route,
        status: reads[p.id].status,
        line: reads[p.id].lines[0] ?? "",
      })),
    };
    void writeFile(STATUS, JSON.stringify(payload, null, 2));
  }, [STATUS, layout, page.path, reads]);

  const onKey = useRef<(key: Key) => void>(() => {});
  onKey.current = (key) => {
    const name = key.name ?? "";
    if (modeRef.current === "goto") {
      if (name === "escape") {
        setMode("desk");
        setDraft("");
      }
      return;
    }
    if (name === "q") {
      renderer.destroy();
      return;
    }
    if (name === "/" || key.sequence === "/") {
      setMode("goto");
      setDraft("");
      setNote("");
      return;
    }
    if (name === "escape") {
      setFocus(-1);
      setNote("");
      return;
    }
    if (name === "tab") {
      const n = layoutRef.current.length;
      setFocus((f) => {
        if (key.shift) return f <= 0 ? -1 : f - 1;
        if (f < 0) return n ? 0 : -1;
        return f + 1 >= n ? -1 : f + 1;
      });
      return;
    }
    const dx = name === "left" || name === "h" ? -1 : name === "right" || name === "l" ? 1 : 0;
    const dy = name === "up" || name === "k" ? -1 : name === "down" || name === "j" ? 1 : 0;
    if (dx === 0 && dy === 0) return;
    if (focusRef.current < 0) {
      if (dy === 0) {
        if (dx > 0 && layoutRef.current.length) setFocus(0);
        return;
      }
      setPageIndex((i) => Math.max(0, Math.min(PAGES.length - 1, i + dy)));
      setNote("");
      return;
    }
    const id = layoutRef.current[focusRef.current]?.id;
    if (!id) return;
    const next = nudge(layoutRef.current, id, dx, dy, Boolean(key.shift));
    if (!next) {
      setNote("no room");
      return;
    }
    setLayout(next);
    setNote(key.shift ? "resized" : "moved");
  };
  useKeyboard((key) => onKey.current(key));

  const go = (raw: string) => {
    const next = pageByPath(raw.trim());
    if (!next) {
      setNote("no such page");
      setMode("desk");
      return;
    }
    setPageIndex(PAGES.findIndex((p) => p.path === next.path));
    setMode("desk");
    setDraft("");
    setNote("");
  };

  const selected = focus >= 0 ? layout[focus] : undefined;
  const footer = [
    "tab block",
    "arrows move",
    "shift+arrows resize",
    "/ path",
    "q quit",
    selected ? `${selected.id} ${selected.x},${selected.y} ${selected.w}×${selected.h}` : page.path,
    note,
  ]
    .filter(Boolean)
    .join("   ");

  return (
    <box width="100%" height="100%" flexDirection="column" backgroundColor={BG}>
      <box height={1} paddingLeft={1} flexDirection="row">
        <text fg={GOLD}>digiquant</text>
        <text fg={DIM}>{`  ${page.label}  ${page.path}  ${API}`}</text>
      </box>
      <box flexGrow={1} flexDirection="row">
        <box width={24} border borderColor={focus < 0 ? GOLD : LINE} title="pages" flexDirection="column">
          {PAGES.map((item, i) => {
            const current = i === pageIndex;
            const indent = item.path.split("/").filter(Boolean).length > 1 ? "  " : "";
            return (
              <text key={item.path} fg={current ? GOLD : DIM}>
                {`${current ? "›" : " "} ${indent}${item.label}`}
              </text>
            );
          })}
        </box>
        <box flexGrow={1} position="relative" overflow="hidden">
          {layout.map((placement, i) => {
            const def = BLOCKS[placement.id];
            const read = reads[placement.id];
            const status = read?.status ?? "loading";
            const lines = read?.lines ?? ["loading…"];
            const on = i === focus;
            return (
              <box
                key={placement.id}
                position="absolute"
                left={share(placement.x - 1, COLS)}
                top={share(placement.y - 1, ROWS)}
                width={share(placement.w, COLS)}
                height={share(placement.h, ROWS)}
                border
                borderColor={on ? GOLD : status === "ok" ? OK : status === "empty" || status === "loading" ? LINE : BAD}
                title={def.title}
                titleColor={on ? GOLD : DIM}
                bottomTitle={read?.asOf ? `as of ${read.asOf}` : def.route}
                overflow="hidden"
                zIndex={on ? 1 : 0}
                paddingLeft={1}
                paddingRight={1}
              >
                <text fg={tone(status)}>{lines.slice(0, 14).join("\n")}</text>
              </box>
            );
          })}
        </box>
      </box>
      <box height={1} paddingLeft={1} flexDirection="row">
        {mode === "goto" ? (
          <>
            <text fg={GOLD}>path </text>
            <input flexGrow={1} focused value={draft} onInput={setDraft} onSubmit={go} />
          </>
        ) : (
          <text fg={DIM}>{footer}</text>
        )}
      </box>
    </box>
  );
}
