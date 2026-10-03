import { writeFile } from "node:fs/promises";
import { useKeyboard, useRenderer } from "@opentui/react";
import { useEffect, useRef, useState } from "react";
import { WEB_SLOTS } from "../../../apps/digiquant-web/components/desk/web-slots";
import { BLOCKS, layoutFor, layoutMatchesPage, pageByPath } from "./catalog";
import {
  COMMAND_LIMIT,
  deskChoices,
  deskIndex,
  isPublicPage,
  publicRailPaths,
  publicRailRows,
  searchCommandPages,
  type CommandHit,
} from "./command";
import { COLS, ROWS, nudge, type Layout } from "./grid";
import { MARK_COLS, MARK_ROWS, REVEAL_MS, glintCell, markDirection, markElapsed, markLines, revealedColumns } from "./mark";
import { BriefPage } from "./pages/brief";
import { PipelinePage } from "./pages/pipeline";
import { PortfolioPages, isPortfolioPath } from "./pages/portfolio";
import { StrategiesPages } from "./pages/strategies";
import { deskForPath, railLine } from "./rail";
import { readBlock, type ReadResult } from "./read";
import { ACCENT, BG, DANGER, DOWN, HAIR, HAIR_STRONG, INK, MUTE, SOFT, UP, WASH } from "./theme";

const API = (process.env.DQ_API_URL ?? "http://127.0.0.1:8788").replace(/\/+$/, "");
const STATUS = process.env.DQ_TUI_STATUS;

type Key = { name?: string; shift?: boolean; sequence?: string };

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

const STRATEGY_PATHS = new Set(["/strategies", "/strategies/detail", "/strategies/deploy"]);
const WEB_ONLY = new Set<string>(WEB_SLOTS.map((slot) => slot.path));
const tone = (status: ReadResult["status"] | "loading") => {
  if (status === "ok") return INK;
  if (status === "empty" || status === "loading") return MUTE;
  return DANGER;
};

function PixelMark() {
  const [now, setNow] = useState(() => Date.now());
  useEffect(() => {
    const timer = setInterval(() => setNow(Date.now()), 100);
    return () => clearInterval(timer);
  }, []);
  const elapsed = markElapsed(now);
  const revealing = elapsed < REVEAL_MS;
  const lines = markLines(revealedColumns(elapsed));
  const glint = glintCell(elapsed);
  return (
    <box width={MARK_COLS} height={MARK_ROWS} flexDirection="column">
      {lines.map((line, row) => (
        <text key={row}>
          {[...line].map((ch, col) => {
            const glinting = glint !== null && glint.row === row && glint.col === col;
            const fg = glinting
              ? ACCENT
              : revealing && ch !== " "
                ? markDirection(row, col) === "up"
                  ? UP
                  : DOWN
                : INK;
            return (
              <span key={col} fg={fg}>
                {ch}
              </span>
            );
          })}
        </text>
      ))}
    </box>
  );
}

function DeskList({
  current,
  cursor,
  onPick,
}: {
  current: string;
  cursor: number;
  onPick: (id: string) => void;
}) {
  return (
    <box width="100%" border borderColor={HAIR_STRONG} backgroundColor={BG} flexDirection="column">
      {deskChoices().map((choice, index) => {
        const on = index === cursor;
        const here = choice.id === current;
        return (
          <box
            key={choice.id}
            flexDirection="column"
            backgroundColor={on ? WASH : BG}
            onMouseDown={() => onPick(choice.id)}
          >
            <box height={1} paddingLeft={1} paddingRight={1} overflow="hidden">
              <text fg={on || here ? ACCENT : INK}>{`${here ? "▸ " : "  "}${choice.label}`}</text>
            </box>
            <box height={1} paddingLeft={1} paddingRight={1} overflow="hidden">
              <text fg={MUTE}>{choice.blurb}</text>
            </box>
          </box>
        );
      })}
    </box>
  );
}

function PathHits({
  hits,
  selected,
  onPick,
}: {
  hits: CommandHit[];
  selected: number;
  onPick: (path: string) => void;
}) {
  if (hits.length === 0) {
    return (
      <box height={1} paddingLeft={1} border borderColor={HAIR_STRONG} backgroundColor={BG}>
        <text fg={MUTE}>no matching pages</text>
      </box>
    );
  }
  return (
    <box width="100%" border borderColor={HAIR_STRONG} backgroundColor={BG} flexDirection="column">
      {hits.map((item, index) => (
        <box
          key={item.path}
          height={1}
          paddingLeft={1}
          paddingRight={1}
          flexDirection="row"
          backgroundColor={index === selected ? WASH : BG}
          overflow="hidden"
          onMouseDown={() => onPick(item.path)}
        >
          <text fg={index === selected ? ACCENT : INK}>{item.path}</text>
          <box flexGrow={1} />
          <text fg={MUTE}>{item.label}</text>
        </box>
      ))}
    </box>
  );
}

function canOpen(path: string): boolean {
  if (!isPublicPage(path)) return false;
  return deskChoices().some((desk) => publicRailPaths(desk.id).includes(path));
}

function isWebSlot(path: string): boolean {
  return WEB_ONLY.has(path) && canOpen(path);
}

/** Dedicated pages paint themselves. Any other public catalog path keeps the grid. */
function isCatalogPath(path: string): boolean {
  if (!canOpen(path) || isWebSlot(path)) return false;
  if (path === "/brief" || path === "/pipeline") return false;
  if (isPortfolioPath(path) || STRATEGY_PATHS.has(path)) return false;
  return true;
}

function mountedView(path: string) {
  if (path === "/brief") return <BriefPage />;
  if (isPortfolioPath(path)) return <PortfolioPages path={path} api={API} />;
  if (path === "/pipeline") return <PipelinePage api={API} />;
  if (STRATEGY_PATHS.has(path)) return <StrategiesPages path={path} api={API} />;
  return null;
}

function publicDeskId(path: string): string {
  const owner = deskForPath(path);
  return deskChoices().find((desk) => desk.id === owner)?.id ?? deskChoices()[0]?.id ?? "baseline";
}

export function App() {
  const renderer = useRenderer();
  const arg = process.argv.find((entry) => entry.startsWith("/") && canOpen(entry));
  const start = arg && canOpen(arg) ? arg : "/brief";
  const [path, setPath] = useState(start);
  const [desk, setDesk] = useState(() => publicDeskId(start));
  const [layout, setLayout] = useState<Layout>(() => layoutFor(start));
  const [focus, setFocus] = useState(-1);
  const [mode, setMode] = useState<"desk" | "path">("desk");
  const [draft, setDraft] = useState("");
  const [hitIndex, setHitIndex] = useState(0);
  const [deskOpen, setDeskOpen] = useState(false);
  const [deskCursor, setDeskCursor] = useState(() => deskIndex(publicDeskId(start)));
  const [note, setNote] = useState("");
  const [reads, setReads] = useState<Record<string, ReadResult>>({});

  const pathRef = useRef(path);
  const deskRef = useRef(desk);
  const layoutRef = useRef(layout);
  const focusRef = useRef(focus);
  const modeRef = useRef(mode);
  const draftRef = useRef(draft);
  const hitIndexRef = useRef(hitIndex);
  const deskOpenRef = useRef(deskOpen);
  const deskCursorRef = useRef(deskCursor);
  const catalogRef = useRef(true);
  pathRef.current = path;
  deskRef.current = desk;
  layoutRef.current = layout;
  focusRef.current = focus;
  modeRef.current = mode;
  draftRef.current = draft;
  hitIndexRef.current = hitIndex;
  deskOpenRef.current = deskOpen;
  deskCursorRef.current = deskCursor;

  const page = pageByPath(path);
  catalogRef.current = isCatalogPath(path);
  const aligned = page ? layoutMatchesPage(path, layout) : false;
  const shown = aligned ? layout : layoutFor(path);
  const shownReads = aligned ? reads : {};
  const shownFocus = aligned ? focus : -1;
  const rows = publicRailRows(desk);
  const hits = mode === "path" ? searchCommandPages(draft, desk).slice(0, COMMAND_LIMIT) : [];
  const selectedHit = hits.length ? Math.min(hitIndex, hits.length - 1) : 0;
  const deskLabelText = deskChoices().find((choice) => choice.id === desk)?.label ?? "Baseline";

  const openPath = (next: string) => {
    if (!canOpen(next) || next === pathRef.current) return;
    const owner = publicDeskId(next);
    const placements = layoutFor(next);
    pathRef.current = next;
    deskRef.current = owner;
    layoutRef.current = placements;
    focusRef.current = -1;
    setPath(next);
    setDesk(owner);
    setLayout(placements);
    setFocus(-1);
    setReads({});
    setNote("");
  };

  const chooseDesk = (id: string) => {
    if (!deskChoices().some((choice) => choice.id === id)) return;
    setDeskOpen(false);
    if (id === deskRef.current) return;
    const home = publicRailPaths(id)[0];
    if (home) openPath(home);
  };

  const openHit = (next: string) => {
    openPath(next);
    setMode("desk");
    setDraft("");
    setHitIndex(0);
    hitIndexRef.current = 0;
    setDeskOpen(false);
  };

  const startPath = () => {
    setMode("path");
    setDeskOpen(false);
    setDraft("");
    setHitIndex(0);
    draftRef.current = "";
    hitIndexRef.current = 0;
    setNote("");
  };

  const startDesk = () => {
    setMode("desk");
    setDraft("");
    setHitIndex(0);
    setDeskCursor(deskIndex(deskRef.current));
    setDeskOpen(true);
  };

  const onDraft = (value: string) => {
    draftRef.current = value;
    hitIndexRef.current = 0;
    setDraft(value);
    setHitIndex(0);
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
    if (layout.some((placement) => !reads[placement.id])) return;
    const payload = {
      path,
      blocks: layout.map((placement) => ({
        id: placement.id,
        route: BLOCKS[placement.id].route,
        status: reads[placement.id].status,
        line: reads[placement.id].lines[0] ?? "",
      })),
    };
    void writeFile(STATUS, JSON.stringify(payload, null, 2));
  }, [STATUS, layout, path, page, reads]);

  const onKey = useRef<(key: Key) => void>(() => {});
  onKey.current = (key) => {
    const name = key.name ?? "";
    if (modeRef.current === "path") {
      if (name === "escape") {
        setMode("desk");
        setDraft("");
        setHitIndex(0);
        return;
      }
      if (name === "up" || name === "down") {
        const count = searchCommandPages(draftRef.current, deskRef.current).slice(0, COMMAND_LIMIT).length;
        if (!count) return;
        const next =
          name === "up"
            ? Math.max(hitIndexRef.current - 1, 0)
            : Math.min(hitIndexRef.current + 1, count - 1);
        hitIndexRef.current = next;
        setHitIndex(next);
      }
      return;
    }
    if (name === "q") {
      renderer.destroy();
      return;
    }
    if (name === "d") {
      if (deskOpenRef.current) {
        setDeskOpen(false);
        return;
      }
      setDeskCursor(deskIndex(deskRef.current));
      setDeskOpen(true);
      return;
    }
    if (name === "/" || key.sequence === "/") {
      startPath();
      return;
    }
    if (deskOpenRef.current) {
      if (name === "escape") {
        setDeskOpen(false);
        return;
      }
      if (name === "enter") {
        const choice = deskChoices()[deskCursorRef.current];
        if (choice) chooseDesk(choice.id);
        return;
      }
      const move = name === "up" || name === "k" ? -1 : name === "down" || name === "j" ? 1 : 0;
      if (move !== 0) {
        const count = deskChoices().length;
        const next = Math.min(Math.max(deskCursorRef.current + move, 0), Math.max(count - 1, 0));
        deskCursorRef.current = next;
        setDeskCursor(next);
      }
      return;
    }
    if (name === "escape") {
      setFocus(-1);
      setNote("");
      return;
    }
    if (name === "tab") {
      if (!catalogRef.current) return;
      const count = layoutRef.current.length;
      setFocus((current) => {
        if (key.shift) return current <= 0 ? -1 : current - 1;
        if (current < 0) return count ? 0 : -1;
        return current + 1 >= count ? -1 : current + 1;
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
      const pages = publicRailPaths(deskRef.current);
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
    const text = typeof raw === "string" ? raw : draftRef.current;
    const found = searchCommandPages(text, deskRef.current).slice(0, COMMAND_LIMIT);
    const picked = found[Math.min(hitIndexRef.current, Math.max(found.length - 1, 0))];
    if (!picked) {
      setNote("no such page");
      setMode("desk");
      setDraft("");
      setHitIndex(0);
      return;
    }
    openHit(picked.path);
  };

  const catalog = isCatalogPath(path);
  const undrawn = isWebSlot(path);
  const view = catalog || undrawn ? null : mountedView(path);
  const selected = catalog && shownFocus >= 0 ? shown[shownFocus] : undefined;
  const footer =
    mode === "path"
      ? "↑↓ choose   enter open   esc"
      : deskOpen
        ? "↑↓ desk   enter   esc   d close"
        : [
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
      <box flexShrink={0} flexDirection="column" backgroundColor={BG}>
        <box flexDirection="row">
          <box paddingLeft={1} paddingRight={1}>
            <PixelMark />
          </box>
          <box flexGrow={1} flexDirection="column">
            <box height={MARK_ROWS} flexDirection="column" justifyContent="center">
              <box height={1} flexDirection="row" alignItems="center" paddingRight={1}>
                <box paddingRight={2} onMouseDown={() => (deskOpen ? setDeskOpen(false) : startDesk())}>
                  <text fg={SOFT}>{`desk: ${deskLabelText} ▾`}</text>
                </box>
                <box flexGrow={1} onMouseDown={() => startPath()}>
                  {mode === "path" ? (
                    <input
                      flexGrow={1}
                      focused
                      value={draft}
                      placeholder="/ go to…"
                      placeholderColor={MUTE}
                      backgroundColor={BG}
                      textColor={INK}
                      focusedBackgroundColor={WASH}
                      focusedTextColor={INK}
                      onInput={onDraft}
                      onSubmit={go}
                    />
                  ) : (
                    <text fg={INK}>{path}</text>
                  )}
                </box>
              </box>
            </box>
            {deskOpen ? <DeskList current={desk} cursor={deskCursor} onPick={chooseDesk} /> : null}
          </box>
        </box>
        <box height={1} border={["bottom"]} borderColor={HAIR} />
      </box>
      <box flexGrow={1} flexDirection="row">
        <box width={36} border={["right"]} borderColor={HAIR_STRONG} flexDirection="column" flexShrink={0}>
          <box height={1} paddingLeft={1} paddingRight={1} border={["bottom"]} borderColor={HAIR}>
            <text fg={MUTE}>~/pages</text>
          </box>
          {rows.map((row) =>
            row.kind === "title" ? (
              <box key={row.text} height={1} paddingLeft={1}>
                <text fg={MUTE}>{row.text}</text>
              </box>
            ) : (
              <box key={row.path} height={1} paddingLeft={1} paddingRight={1} backgroundColor={row.path === path ? WASH : BG}>
                <text fg={row.path === path ? ACCENT : SOFT}>{railLine(row)}</text>
              </box>
            ),
          )}
        </box>
        <box flexGrow={1} position="relative" overflow="hidden">
          {undrawn ? (
            <box paddingLeft={1} paddingTop={1}>
              <text fg={MUTE}>This page is not drawn on the terminal.</text>
            </box>
          ) : (
            (view ??
              shown.map((placement, index) => {
                const def = BLOCKS[placement.id];
                const read = shownReads[placement.id];
                const status = read?.status ?? "loading";
                const lines = read?.lines ?? ["loading…"];
                const on = index === shownFocus;
                const border =
                  on ? ACCENT : status === "empty" || status === "loading" || status === "ok" ? HAIR : DANGER;
                return (
                  <box
                    key={placement.id}
                    position="absolute"
                    left={share(placement.x - 1, COLS)}
                    top={share(placement.y - 1, ROWS)}
                    width={share(placement.w, COLS)}
                    height={share(placement.h, ROWS)}
                    border
                    borderColor={border}
                    title={def.title}
                    titleColor={on ? ACCENT : MUTE}
                    bottomTitle={read?.asOf ? `as of ${read.asOf}` : def.route}
                    overflow="hidden"
                    zIndex={on ? 1 : 0}
                    paddingLeft={1}
                    paddingRight={1}
                  >
                    <text fg={tone(status)}>{lines.slice(0, 14).join("\n")}</text>
                  </box>
                );
              }))
          )}
          {mode === "path" ? (
            <box position="absolute" top={0} left={0} width="100%" zIndex={8} backgroundColor={BG}>
              <PathHits hits={hits} selected={selectedHit} onPick={openHit} />
            </box>
          ) : null}
        </box>
      </box>
      <box height={1} paddingLeft={1} paddingRight={1} border={["top"]} borderColor={HAIR} flexDirection="row">
        <text fg={MUTE}>{footer}</text>
      </box>
    </box>
  );
}
