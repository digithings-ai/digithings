"use client";

import { useEffect, useRef, useState, type CSSProperties, type KeyboardEvent, type RefObject } from "react";
import { Button } from "@digithings/ui/ui";
import { expandLayout, type Need } from "../../../../../clients/digiquant-tui/src/expand";
import { COLS, ROWS, type Layout, type Placement } from "../../../../../clients/digiquant-tui/src/grid";
import { shapeLines, tidyBody, type PaneBody, type PaneBlock } from "../../../../../clients/digiquant-tui/src/pages/shape";
import { bodySize, compactBody, hiddenLabel } from "../../../../../clients/digiquant-tui/src/pages/pane-fit";

export const PANE_HINT = "[tab] next";
export const OPEN_HINT = "[enter] open";
export const CLOSE_HINT = "[esc] close";

/** 12×12 mosaic. One hairline between panes, not a second frame plus a gutter.
 *  On a phone, `.desk-mosaic` stacks each pane to the full width. */
export const PANE_GRID = "desk-mosaic grid h-full min-h-0 w-full min-w-0 flex-1 grid-cols-12 grid-rows-12 gap-px bg-hair p-px";

/** The same mosaic with each tile placed by `tileStyle`, so an open tile and its
 *  neighbours ease to their new rects (`.desk-tile`). */
export const PANE_MOSAIC = "desk-mosaic relative h-full min-h-0 w-full min-w-0 flex-1 bg-hair";
export const DESK_TILE = "desk-tile absolute min-h-0 min-w-0";

/** Geist Mono at 0.75rem: one cell is 0.6em wide. */
const CHAR_PX = 7.2;
/** One table row: the 1.45 line, `py-1` and its hairline. */
const ROW_PX = 26;
/** Header, footer and body padding around the content. */
const CHROME_PX = 72;

const PANE_META = "font-mono text-[0.6875rem] font-normal tracking-[0.04em]";
const PANE_COPY = "font-mono text-[0.75rem] leading-[1.45] tabular-nums";

/** A tile's rect as a share of the mosaic. One hairline left and above; the
 *  last column and row keep one on the far edge too. */
export function tileStyle(p: Placement): CSSProperties {
  const share = (cells: number, total: number) => `${(cells / total) * 100}%`;
  return {
    left: `calc(${share(p.x - 1, COLS)} + 1px)`,
    top: `calc(${share(p.y - 1, ROWS)} + 1px)`,
    width: `calc(${share(p.w, COLS)} - ${p.x + p.w - 1 >= COLS ? 2 : 1}px)`,
    height: `calc(${share(p.h, ROWS)} - ${p.y + p.h - 1 >= ROWS ? 2 : 1}px)`,
  };
}

type MosaicState = { key: string; focus: string; open: string | null; need?: Need };

export type PaneControls = {
  id: string;
  focused: boolean;
  open: boolean;
  onFocus: () => void;
  onNext: () => void;
  onStep: (delta: number) => void;
  onToggle: (px: { w: number; h: number }) => void;
  onClose: () => void;
};

/**
 * Focus and the one open tile, like the site's module mosaic: the open tile
 * grows in place from its top-left and the others repack around it
 * (`expandLayout`). Tab or the arrows move focus, Enter or a click opens,
 * Esc closes, and focus stays on the tile.
 */
export function useDeskMosaic(layout: Layout): {
  mount: (node: HTMLDivElement | null) => void;
  style: (id: string) => CSSProperties;
  pane: (id: string) => PaneControls;
} {
  const ids = layout.map((placement) => placement.id);
  const key = ids.join("|");
  const [stored, setState] = useState<MosaicState>({ key, focus: ids[0] ?? "", open: null });
  const [grid, mount] = useState<HTMLDivElement | null>(null);
  const state: MosaicState = stored.key === key ? stored : { key, focus: ids[0] ?? "", open: null };
  const shown = expandLayout(layout, state.open, state.need);
  const cells = (px: { w: number; h: number }): Need | undefined => {
    if (!grid || !grid.clientWidth || !grid.clientHeight) return undefined;
    return { w: px.w / (grid.clientWidth / COLS), h: px.h / (grid.clientHeight / ROWS) };
  };
  const step = (delta: number) => {
    if (!ids.length) return;
    const index = Math.max(ids.indexOf(state.focus), 0);
    const id = ids[(index + delta + ids.length) % ids.length] ?? ids[0] ?? "";
    setState({ ...state, focus: id });
    grid?.querySelector<HTMLElement>(`[data-pane="${CSS.escape(id)}"] [data-pane-toggle]`)?.focus();
  };
  return {
    mount,
    style: (id) => {
      const placement = shown.find((p) => p.id === id);
      return placement ? tileStyle(placement) : {};
    },
    pane: (id) => ({
      id,
      focused: state.focus === id,
      open: state.open === id,
      onFocus: () => {
        if (state.focus !== id) setState({ ...state, focus: id });
      },
      onNext: () => step(1),
      onStep: step,
      onToggle: (px) => setState(state.open === id ? { ...state, focus: id, open: null } : { key, focus: id, open: id, need: cells(px) }),
      onClose: () => setState({ ...state, focus: id, open: null }),
    }),
  };
}

function BlockView({ block }: { block: PaneBlock }) {
  switch (block.kind) {
    case "sentence":
      return <p className="m-0 whitespace-pre-wrap">{block.text}</p>;
    case "stat":
      return <p className="m-0 text-ink-mute">{block.text}</p>;
    case "chart":
      return <p className="m-0 whitespace-pre">{block.text}</p>;
    case "table":
      return (
        <table className="desk-pane-table w-full border-collapse text-left">
          {block.columns.length ? (
            <thead>
              <tr>
                {block.columns.map((column) => (
                  <th key={column} className="border-b border-hair px-2 py-1 text-left font-normal uppercase tracking-[0.06em] text-ink-mute">
                    {column}
                  </th>
                ))}
              </tr>
            </thead>
          ) : null}
          <tbody>
            {block.rows.map((row, index) => (
              <tr key={index} className="border-b border-hair last:border-b-0">
                {row.map((cell, cellIndex) => (
                  <td key={cellIndex} className="px-2 py-1 align-top">
                    {cell}
                  </td>
                ))}
              </tr>
            ))}
          </tbody>
        </table>
      );
    default: {
      const exhaustive: never = block;
      return <p className="m-0">{String(exhaustive)}</p>;
    }
  }
}

/** Body padding (`px-2.5`), both sides, in px. */
const BODY_PAD = 20;

/** Characters across and table rows down the body fits. Null until measured, and where ResizeObserver is missing. */
function useBodyFit(): { ref: RefObject<HTMLDivElement | null>; fit: { chars: number; rows: number } | null } {
  const ref = useRef<HTMLDivElement | null>(null);
  const [fit, setFit] = useState<{ chars: number; rows: number } | null>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const measure = () => {
      const chars = Math.max(1, Math.floor((node.clientWidth - BODY_PAD) / CHAR_PX));
      const rows = Math.max(1, Math.floor((node.clientHeight - BODY_PAD) / ROW_PX) - 1);
      setFit((prev) => (prev && prev.chars === chars && prev.rows === rows ? prev : { chars, rows }));
    };
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, fit };
}

/** Same chrome as the terminal pane: one-row header, body, footer.
 *  Like the site's module cards, a closed tile shows its key view: the table
 *  columns and rows that fit, the recent end of each chart, the start of the
 *  prose. Open, it grows in place and shows everything. */
export function DeskPane({
  title,
  route,
  asOf,
  lines,
  blocks,
  tone,
  id,
  focused,
  open,
  onFocus,
  onNext,
  onStep,
  onToggle,
  onClose,
}: {
  title: string;
  route: string;
  asOf: string | null;
  lines?: string[];
  blocks?: PaneBody;
  tone: string;
} & PaneControls) {
  const body = tidyBody(blocks ?? shapeLines(lines ?? []));
  const status = asOf ? `as of ${asOf}` : route;
  const { ref: bodyRef, fit } = useBodyFit();
  const face = open || fit === null ? { body, hidden: null } : compactBody(body, fit);
  const more = face.hidden ? hiddenLabel(face.hidden) : null;
  const toggle = () => {
    const size = bodySize(body);
    onToggle({ w: size.chars * CHAR_PX + BODY_PAD, h: size.lines * ROW_PX + CHROME_PX });
  };
  const onKeyDown = (event: KeyboardEvent<HTMLElement>) => {
    if (event.key === "Escape" && open) {
      event.preventDefault();
      onClose();
      return;
    }
    const delta = event.key === "ArrowRight" || event.key === "ArrowDown" ? 1 : event.key === "ArrowLeft" || event.key === "ArrowUp" ? -1 : 0;
    if (delta === 0 || !(event.target instanceof HTMLElement) || !event.target.hasAttribute("data-pane-toggle")) return;
    event.preventDefault();
    onStep(delta);
  };
  return (
    <section
      aria-label={title}
      data-pane={id}
      data-route={route}
      data-focused={focused ? "1" : "0"}
      data-open={open ? "1" : "0"}
      onKeyDown={onKeyDown}
      className={`flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-surface ${focused ? "shadow-[inset_0_0_0_1px_var(--ink)]" : ""}`}
    >
      <header className="flex h-7 shrink-0 items-center border-b border-hair">
        <Button
          type="button"
          variant="ghost"
          size="xs"
          data-pane-toggle=""
          aria-expanded={open}
          className={`h-7 w-full justify-start rounded-none px-2.5 ${PANE_META} ${focused ? "text-ink" : "text-ink-mute"}`}
          onFocus={onFocus}
          onClick={toggle}
        >
          <span className="truncate">{title}</span>
        </Button>
      </header>
      <div
        ref={bodyRef}
        className={`desk-pane-body flex min-h-0 flex-1 flex-col gap-1.5 overflow-auto px-2.5 py-1.5 ${PANE_COPY} ${tone}`}
        onClick={() => {
          if (window.getSelection()?.toString()) return;
          toggle();
        }}
      >
        {face.body.blocks.map((block, index) => <BlockView key={index} block={block} />)}
      </div>
      <footer className={`flex h-7 shrink-0 items-center justify-between gap-2 border-t border-hair px-2.5 text-ink-mute ${PANE_META}`}>
        <span className="truncate tabular-nums">{more ? `${status} · ${more}` : status}</span>
        {focused ? (
          <span className="flex shrink-0 items-center gap-2">
            <span>{open ? CLOSE_HINT : OPEN_HINT}</span>
            <Button type="button" variant="ghost" size="xs" className={`h-7 shrink-0 rounded-none px-0 ${PANE_META} text-ink-mute`} onClick={onNext}>
              {PANE_HINT}
            </Button>
          </span>
        ) : (
          <span />
        )}
      </footer>
    </section>
  );
}
