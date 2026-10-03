import { writeFile } from "node:fs/promises";
import { useKeyboard, useRenderer } from "@opentui/react";
import { useEffect, useRef, useState } from "react";
import { WEB_SLOTS } from "../../../apps/digiquant-web/components/desk/web-slots";
import { BLOCKS, layoutFor, layoutMatchesPage, pageByPath } from "./catalog";
import { COLS, ROWS, nudge, type Layout } from "./grid";
import { MARK_COLS, MARK_ROWS, markLines } from "./mark";
import { BriefPage } from "./pages/brief";
import { FxDesk, isFxPath } from "./pages/fx";
import { PipelinePage } from "./pages/pipeline";
import { PortfolioPages, isPortfolioPath } from "./pages/portfolio";
import { StrategiesPages } from "./pages/strategies";
import { deskForPath, deskLabel, railLine, railPaths, railRows } from "./rail";
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

const STRATEGY_PATHS = new Set(["/strategies", "/strategies/detail", "/strategies/deploy"]);
const WEB_ONLY = new Set<string>(WEB_SLOTS.map((slot) => slot.path));
const MARK = markLines();

const tone = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return INK;
  if (status === "empty") return DIM;
  if (status === "loading") return DIM;
  return BAD;
};

function isWebSlot(path: string): boolean {
  return WEB_ONLY.has(path);
}

/** Dedicated pages paint themselves. Any other catalog path keeps the grid. */
function isCatalogPath(path: string): boolean {
  if (isWebSlot(path)) return false;
  if (path === "/brief" || path === "/pipeline") return false;
  if (isPortfolioPath(path) || STRATEGY_PATHS.has(path) || isFxPath(path)) return false;
  return true;
}

function mountedView(path: string) {
  if (path === "/brief") return <BriefPage />;
  if (isPortfolioPath(path)) return <PortfolioPages path={path} api={API} />;
  if (path === "/pipeline") return <PipelinePage api={API} />;
  if (STRATEGY_PATHS.has(path)) return <StrategiesPages path={path} api={API} />;
  if (isFxPath(path)) return <FxDesk path={path} api={API} />;
  return null;
}

export function App() {
  const renderer = useRenderer();
  const arg = process.argv.find((a) => a.startsWith("/") && (pageByPath(a) || isWebSlot(a)));
  const start = arg && (pageByPath(arg) || isWebSlot(arg)) ? arg : "/brief";
  const [path, setPath] = useState(start);
  const [desk, setDesk] = useState(() => deskForPath(start) ?? "baseline");
  const [layout, setLayout] = useState<Layout>(() => layoutFor(start));
  const [focus, setFocus] = useState(-1);
  const [mode, setMode] = useState<"desk" | "goto">("desk");
  const [draft, setDraft] = useState("");
  const [note, setNote] = useState("");
  const [reads, setReads] = useState<Record<string, ReadResult>>({});

  const pathRef = useRef(path);
  const deskRef = useRef(desk);
  const layoutRef = useRef(layout);
  const focusRef = useRef(focus);
  const modeRef = useRef(mode);
  const catalogRef = useRef(true);
  pathRef.current = path;
  deskRef.current = desk;
  layoutRef.current = layout;
  focusRef.current = focus;
  modeRef.current = mode;

  const page = pageByPath(path);
  catalogRef.current = isCatalogPath(path);
  const aligned = page ? layoutMatchesPage(path, layout) : false;
  const shown = aligned ? layout : layoutFor(path);
  const shownReads = aligned ? reads : {};
  const shownFocus = aligned ? focus : -1;
  const rows = railRows(desk);

  const openPath = (next: string) => {
    if (next === pathRef.current) return;
    const owner = deskForPath(next);
    const placements = layoutFor(next);
    pathRef.current = next;
    if (owner) deskRef.current = owner;
    layoutRef.current = placements;
    focusRef.current = -1;
    setPath(next);
    if (owner) setDesk(owner);
    setLayout(placements);
    setFocus(-1);
    setReads({});
    setNote("");
  };

  useEffect(() => {
    if (!isCatalogPath(path)) return;
    const placements = layoutFor(path);
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
  }, [path]);

  useEffect(() => {
    if (!STATUS) return;
    if (!page || !layoutMatchesPage(path, layout)) return;
    if (layout.some((p) => !reads[p.id])) return;
    const payload = {
      path,
      blocks: layout.map((p) => ({
        id: p.id,
        route: BLOCKS[p.id].route,
        status: reads[p.id].status,
        line: reads[p.id].lines[0] ?? "",
      })),
    };
    void writeFile(STATUS, JSON.stringify(payload, null, 2));
  }, [STATUS, layout, path, page, reads]);

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
    if (name === "d") {
      const nextDesk = deskRef.current === "baseline" ? "fx" : "baseline";
      const home = railPaths(nextDesk)[0];
      if (!home) return;
      deskRef.current = nextDesk;
      setDesk(nextDesk);
      openPath(home);
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
      if (!catalogRef.current) return;
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
    if (focusRef.current < 0 || !catalogRef.current) {
      if (dy === 0) {
        if (dx > 0 && catalogRef.current && layoutRef.current.length) setFocus(0);
        return;
      }
      const pages = railPaths(deskRef.current);
      const index = pages.indexOf(pathRef.current);
      const next = pages[index + dy];
      if (next) openPath(next);
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
    const query = raw.trim();
    const next = pageByPath(query) ?? (isWebSlot(query) ? query : undefined);
    if (!next) {
      setNote("no such page");
      setMode("desk");
      return;
    }
    openPath(typeof next === "string" ? next : next.path);
    setMode("desk");
    setDraft("");
  };

  const catalog = isCatalogPath(path);
  const undrawn = isWebSlot(path);
  const view = catalog || undrawn ? null : mountedView(path);
  const selected = catalog && shownFocus >= 0 ? shown[shownFocus] : undefined;
  const footer = [
    catalog ? (selected ? "tab block   arrows move   shift+arrows resize" : "↑↓ page   → block") : "↑↓ page",
    "d desk",
    "/ path",
    "q quit",
    selected ? `${selected.id} ${selected.x},${selected.y} ${selected.w}×${selected.h}` : path,
    note,
  ]
    .filter(Boolean)
    .join("   ");

  return (
    <box width="100%" height="100%" flexDirection="column" backgroundColor={BG}>
      <box height={MARK_ROWS} flexDirection="row" backgroundColor={BG}>
        <box flexGrow={1} paddingLeft={1} flexDirection="column" justifyContent="center">
          <text fg={DIM}>{`desk: ${deskLabel(desk)}`}</text>
          <text fg={INK}>{path}</text>
        </box>
        <box width={MARK_COLS} height={MARK_ROWS} flexDirection="column">
          {MARK.map((line, index) => (
            <text key={index} fg={INK}>{line}</text>
          ))}
        </box>
      </box>
      <box height={1} border={["bottom"]} borderColor={LINE} />
      <box flexGrow={1} flexDirection="row">
        <box width={36} border={["right"]} borderColor={LINE} flexDirection="column" flexShrink={0}>
          <box height={1} paddingLeft={1} paddingRight={1} border={["bottom"]} borderColor={LINE}>
            <text fg={DIM}>~/pages</text>
          </box>
          {rows.map((row) =>
            row.kind === "title" ? (
              <box key={row.text} height={1} paddingLeft={1}>
                <text fg={DIM}>{row.text}</text>
              </box>
            ) : (
              <box key={row.path} height={1} paddingLeft={1} paddingRight={1}>
                <text fg={row.path === path ? GOLD : DIM}>{railLine(row)}</text>
              </box>
            ),
          )}
        </box>
        <box flexGrow={1} position="relative" overflow="hidden">
          {undrawn ? (
            <box paddingLeft={1} paddingTop={1}>
              <text fg={DIM}>This page is not drawn on the terminal.</text>
            </box>
          ) : (view ?? shown.map((placement, i) => {
            const def = BLOCKS[placement.id];
            const read = shownReads[placement.id];
            const status = read?.status ?? "loading";
            const lines = read?.lines ?? ["loading…"];
            const on = i === shownFocus;
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
          }))}
        </box>
      </box>
      <box height={1} paddingLeft={1} paddingRight={1} border={["top"]} borderColor={LINE} flexDirection="row">
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
