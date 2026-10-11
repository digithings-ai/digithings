"use client";

import { useEffect, useRef, useState, type RefObject } from "react";
import { Button, Dialog, DialogContent, DialogDescription, DialogTitle } from "@digithings/ui/ui";
import { shapeLines, type PaneBody, type PaneBlock } from "../../../../../clients/digiquant-tui/src/pages/shape";
import { CHAR_PX, COMPACT_ROWS, compactBody, hiddenLabel } from "./pane-fit";

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
  lines,
  blocks,
  tone,
  focused,
  onFocus,
  onNext,
}: {
  title: string;
  route: string;
  asOf: string | null;
  lines?: string[];
  blocks?: PaneBody;
  tone: string;
  focused: boolean;
  onFocus: () => void;
  onNext: () => void;
}) {
  const body = blocks ?? shapeLines(lines ?? []);
  const status = asOf ? `as of ${asOf}` : route;
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
          <span className="truncate tabular-nums">{more ? `${status} · ${more}` : status}</span>
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
            {body.blocks.map((block, index) => <BlockView key={index} block={block} />)}
          </div>
          <DialogDescription className={`flex h-8 shrink-0 items-center border-t border-hair px-3 text-ink-mute ${PANE_META}`}>{status}</DialogDescription>
        </DialogContent>
      </Dialog>
    </>
  );
}
