"use client";

import { useState } from "react";
import { Button } from "@digithings/ui/ui";
import { shapeLines, type PaneBody, type PaneBlock } from "../../../../../clients/digiquant-tui/src/pages/shape";

export const PANE_HINT = "[tab] next";

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
  if (block.kind === "sentence") return <p className="m-0 whitespace-pre-wrap">{block.text}</p>;
  if (block.kind === "stat") return <p className="m-0 text-ink-mute">{block.text}</p>;
  return (
    <table className="w-full border-collapse text-left">
      {block.columns.length ? (
        <thead>
          <tr>
            {block.columns.map((column) => (
              <th key={column} className="border-b border-hair px-1 py-0.5 text-left font-normal uppercase text-ink-mute">
                {column}
              </th>
            ))}
          </tr>
        </thead>
      ) : null}
      <tbody>
        {block.rows.map((row, index) => (
          <tr key={index} className="border-b border-hair">
            {row.map((cell, cellIndex) => (
              <td key={cellIndex} className="px-1 py-0.5 align-top">
                {cell}
              </td>
            ))}
          </tr>
        ))}
      </tbody>
    </table>
  );
}

/** Same chrome as the terminal pane: one-row header, body, footer. */
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
  return (
    <section
      aria-label={title}
      data-route={route}
      data-focused={focused ? "1" : "0"}
      className={`flex h-full min-h-0 min-w-0 flex-1 flex-col overflow-hidden border bg-surface ${focused ? "border-ink" : "border-hair"}`}
    >
      <header className="flex h-6 shrink-0 items-center border-b border-hair">
        <Button
          type="button"
          variant="ghost"
          size="xs"
          className="h-6 w-full justify-start rounded-none px-2 text-[0.65rem] font-normal text-ink-mute"
          onClick={onFocus}
        >
          <span className="truncate">{title}</span>
        </Button>
      </header>
      <div className={`flex min-h-0 flex-1 flex-col gap-1 overflow-auto px-2 py-1 text-[0.7rem] leading-[1.35] ${tone}`}>{body.blocks.map((block, index) => <BlockView key={index} block={block} />)}</div>
      <footer className="flex h-6 shrink-0 items-center justify-between gap-2 border-t border-hair px-2 text-[0.6rem] text-ink-mute">
        <span className="truncate">{status}</span>
        {focused ? (
          <Button type="button" variant="ghost" size="xs" className="h-5 shrink-0 rounded-none px-1 text-[0.6rem] font-normal text-ink-mute" onClick={onNext}>
            {PANE_HINT}
          </Button>
        ) : (
          <span />
        )}
      </footer>
    </section>
  );
}
