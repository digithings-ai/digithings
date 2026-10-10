"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle } from "@digithings/ui/ui";
import { asOfStatus, toneOf } from "../../../../../clients/digiquant-tui/src/format";
import { shapeLines, type PaneBody, type PaneBlock } from "../../../../../clients/digiquant-tui/src/pages/shape";
import { CHAR_PX, COMPACT_ROWS, compactBody, hiddenLabel } from "./pane-fit";
import { PanelView } from "../panel-view";

export const PANE_HINT = "[tab] next";

/** 12×12 mosaic. One hairline between panes, not a second frame plus a gutter.
 *  On a phone, `.desk-mosaic` stacks each pane to the full width. */
export const PANE_GRID = "desk-mosaic grid h-full min-h-0 w-full min-w-0 flex-1 grid-cols-12 grid-rows-12 gap-px bg-hair p-px";

const PANE_META = "font-mono text-[0.6875rem] font-normal tracking-[0.04em]";
const PANE_COPY = "font-mono text-[0.75rem] leading-[1.45] tabular-nums";

/** Click focuses a pane. The hint moves focus to the next one. */
export function usePaneFocus(ids: string[]): { focus: string; focusAt: (id: string) => void; next: () => void } {
  const key = ids.join("|");
  const [state, setState] = useState({ key, focus: ids[0] ?? "" });
  const focus = state.key === key ? state.focus : (ids[0] ?? "");
  return {
    focus,
    focusAt: (id: string) => setState({ key, focus: id }),
    next: () => {
      if (!ids.length) return;
      const index = ids.indexOf(focus);
      setState({ key, focus: ids[(index + 1) % ids.length] ?? ids[0] ?? "" });
    },
  };
}

/** A signed figure is green or red, read off its sign. Zero and unsigned figures keep the pane ink. */
function toneClass(text: string): string {
  const tone = toneOf(text);
  return tone === "up" ? "text-up" : tone === "down" ? "text-down" : "";
}

/** `label  value   label  value`. Labels stay muted; values take their tone. */
function StatView({ text }: { text: string }) {
  return (
    <p className="m-0 text-ink-mute">
      {text.split("   ").map((pair, index) => {
        const cut = pair.indexOf("  ");
        const label = cut < 0 ? pair : pair.slice(0, cut + 2);
        const value = cut < 0 ? "" : pair.slice(cut + 2);
        return (
          <span key={index}>
            {index > 0 ? "   " : ""}
            {label}
            {value ? <span className={toneClass(value)}>{value}</span> : null}
          </span>
        );
      })}
    </p>
  );
}

const AGE_BADGE: Record<"fresh" | "warn" | "stale", string> = {
  fresh: "border-hair text-ink-mute",
  warn: "border-warn text-warn",
  stale: "border-down text-down",
};

function BlockView({ block }: { block: PaneBlock }) {
  switch (block.kind) {
    case "sentence":
      return <p className="m-0 whitespace-pre-wrap">{block.text}</p>;
    case "stat":
      return <StatView text={block.text} />;
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
                  <td key={cellIndex} className={`px-2 py-1 align-top ${toneClass(cell)}`}>
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

/** Characters the body fits across. Null until measured, and where ResizeObserver is missing. */
function useBodyChars(): { ref: RefObject<HTMLDivElement | null>; chars: number | null } {
  const ref = useRef<HTMLDivElement | null>(null);
  const [chars, setChars] = useState<number | null>(null);
  useEffect(() => {
    const node = ref.current;
    if (!node || typeof ResizeObserver === "undefined") return;
    const measure = () => setChars(Math.max(1, Math.floor((node.clientWidth - BODY_PAD) / CHAR_PX)));
    measure();
    const observer = new ResizeObserver(measure);
    observer.observe(node);
    return () => observer.disconnect();
  }, []);
  return { ref, chars };
}

/** Same chrome as the terminal pane: one-row header, body, footer.
 *  Like the site's module cards, the face is compact: the table columns that
 *  fit, the first rows, the recent end of each chart. A click opens the full
 *  view with everything. */
export function DeskPane({
  title,
  route,
  asOf,
  dataAsOf,
  lines,
  blocks,
  tone,
  focused,
  onFocus,
  onNext,
  panel,
}: {
  title: string;
  route: string;
  asOf: string | null;
  /** The date the payload holds. Shown beside `asOf` when they differ, and aged. */
  dataAsOf?: string | null;
  lines?: string[];
  blocks?: PaneBody;
  tone: string;
  focused: boolean;
  onFocus: () => void;
  onNext: () => void;
  /** The read's data, for a block that can also draw as a chart. Pass it only on an ok read. */
  panel?: { id: string; data: unknown };
}) {
  const body = blocks ?? shapeLines(lines ?? []);
  const painted = body.blocks.map((block, index) => <BlockView key={index} block={block} />);
  const status = asOfStatus(route, asOf, dataAsOf);
  const dates = status.age ? status.label.slice(0, status.label.indexOf(` · ${status.age}`)) : status.label;
  const [open, setOpen] = useState(false);
  const { ref: bodyRef, chars } = useBodyChars();
  const face = chars === null ? { body, hidden: null } : compactBody(body, { chars, rows: COMPACT_ROWS });
  const more = face.hidden ? hiddenLabel(face.hidden) : null;
  const expand = () => {
    onFocus();
    setOpen(true);
  };
  return (
    <>
      <section
        aria-label={title}
        data-route={route}
        data-focused={focused ? "1" : "0"}
        className={`flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden bg-surface ${focused ? "shadow-[inset_0_0_0_1px_var(--ink)]" : ""}`}
      >
        <header className="flex h-7 shrink-0 items-center border-b border-hair">
          <Button
            type="button"
            variant="ghost"
            size="xs"
            className={`h-7 w-full justify-start rounded-none px-2.5 ${PANE_META} ${focused ? "text-ink" : "text-ink-mute"}`}
            aria-haspopup="dialog"
            onClick={expand}
          >
            <span className="truncate">{title}</span>
          </Button>
        </header>
        <div ref={bodyRef} className={`desk-pane-body flex min-h-0 flex-1 flex-col gap-1.5 overflow-auto px-2.5 py-1.5 ${PANE_COPY} ${tone}`} onClick={expand}>
          {face.body.blocks.map((block, index) => <BlockView key={index} block={block} />)}
        </div>
        <footer className={`flex h-7 shrink-0 items-center justify-between gap-2 border-t border-hair px-2.5 text-ink-mute ${PANE_META}`}>
          <span className="flex min-w-0 items-center gap-2">
            <span className="truncate tabular-nums">{more ? `${dates} · ${more}` : dates}</span>
            {status.age && status.state ? (
              <span data-age={status.state} className={`shrink-0 border px-1 leading-[1.2] ${AGE_BADGE[status.state]}`}>
                {status.state === "fresh" ? status.age : `${status.age} · ${status.state}`}
              </span>
            ) : null}
          </span>
          {focused ? (
            <Button type="button" variant="ghost" size="xs" className={`h-7 shrink-0 rounded-none px-0 ${PANE_META} text-ink-mute`} onClick={onNext}>
              {PANE_HINT}
            </Button>
          ) : (
            <span />
          )}
        </footer>
      </section>
      <Dialog open={open} onOpenChange={setOpen}>
        <DialogContent className="flex max-h-[85vh] flex-col gap-0 p-0 sm:max-w-[min(72rem,calc(100%-2rem))]">
          <header className="flex h-8 shrink-0 items-center border-b border-hair px-3 pr-10">
            <DialogTitle className={`truncate ${PANE_META} text-ink`}>{title}</DialogTitle>
          </header>
          <div className={`flex min-h-0 flex-1 flex-col gap-1.5 overflow-auto px-3 py-2 ${PANE_COPY} ${tone}`}>
            {panel ? (
              <PanelView id={panel.id} title={title} data={panel.data}>
                {painted}
              </PanelView>
            ) : (
              painted
            )}
          </div>
          <DialogDescription className={`flex h-8 shrink-0 items-center border-t border-hair px-3 text-ink-mute ${PANE_META}`}>{status.label}</DialogDescription>
        </DialogContent>
      </Dialog>
    </>
  );
}
