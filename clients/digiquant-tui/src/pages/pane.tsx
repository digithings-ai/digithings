import type { BoxRenderable } from "@opentui/core";
import { useKeyboard } from "@opentui/react";
import { useState } from "react";
import { expandLayout } from "../expand";
import { COLS, ROWS, type Layout } from "../grid";
import { toneOf } from "../format";
import { ACCENT, BG, DOWN, HAIR, MUTE, UP } from "../theme";
import { compactBody, hiddenLabel } from "./pane-fit";
import { shapeLines, tidyBody, type PaneBody } from "./shape";

export const PANE_HINT = "[tab] next";
export const OPEN_HINT = "[enter] open";
export const CLOSE_HINT = "[esc] close";

type FocusState = { resetKey: string; focus: number; open: boolean };

/** Tab moves the focused pane. Enter opens it in place, Esc closes it, and
 *  focus stays on it. A click on a pane focuses and opens it, and a second
 *  click closes it. A new reset key returns focus to the first pane, closed. */
export function useFocusedPane(count: number, resetKey = ""): [number, (index: number) => void, boolean] {
  const [state, setState] = useState<FocusState>({ resetKey, focus: 0, open: false });
  const own = state.resetKey === resetKey;
  const focus = own ? state.focus : 0;
  useKeyboard((key) => {
    const name = key.name ?? "";
    if (count <= 0) return;
    if (name === "tab") {
      setState((current) => {
        const index = current.resetKey === resetKey && current.focus >= 0 && current.focus < count ? current.focus : 0;
        const next = key.shift ? (index - 1 + count) % count : (index + 1) % count;
        return { resetKey, focus: next, open: current.resetKey === resetKey && current.open };
      });
      return;
    }
    if (name === "enter" || name === "return") {
      setState((current) => (current.resetKey === resetKey ? { ...current, open: !current.open } : { resetKey, focus: 0, open: true }));
      return;
    }
    if (name === "escape") setState((current) => ({ ...current, resetKey, open: false }));
  });
  const shown = count <= 0 ? 0 : Math.min(focus, count - 1);
  const click = (index: number) =>
    setState((current) =>
      current.resetKey === resetKey && current.focus === index ? { ...current, open: !current.open } : { resetKey, focus: index, open: true },
    );
  return [shown, click, own && state.open && count > 0];
}

/** A signed figure is green or red; everything else keeps the pane ink. */
function toneInk(text: string, ink: string): string {
  const tone = toneOf(text.trim());
  return tone === "up" ? UP : tone === "down" ? DOWN : ink;
}

/** One row of cells, `sep` between them, each cell in its own tone. */
function Toned({ cells, sep, ink }: { cells: string[]; sep: string; ink: string }) {
  return (
    <text fg={ink} flexShrink={0}>
      {cells.map((cell, index) => (
        <span key={index} fg={toneInk(cell, ink)}>
          {index > 0 ? sep : ""}
          {cell}
        </span>
      ))}
    </text>
  );
}

/** A stat line is `label  value   label  value`. Labels stay muted; values take their tone. */
function StatLine({ text }: { text: string }) {
  const pairs = text.split("   ");
  return (
    <text fg={MUTE} flexShrink={0}>
      {pairs.map((pair, index) => {
        const cut = pair.indexOf("  ");
        const label = cut < 0 ? pair : pair.slice(0, cut + 2);
        const value = cut < 0 ? "" : pair.slice(cut + 2);
        return (
          <span key={index} fg={MUTE}>
            {index > 0 ? "   " : ""}
            {label}
            <span fg={toneInk(value, MUTE)}>{value}</span>
          </span>
        );
      })}
    </text>
  );
}

const share = (cells: number, total: number): `${number}%` => `${(cells / total) * 100}%` as `${number}%`;

/** The page layout with the focused pane open in place: it grows, the rest repack. */
export function openLayout(layout: Layout, focus: number, open: boolean): Layout {
  return expandLayout(layout, open ? (layout[focus]?.id ?? null) : null);
}

/** Absolute box props for one block of `layout`, as shares of the page. */
export function paneBox(layout: Layout, id: string) {
  const p = layout.find((placement) => placement.id === id) ?? { x: 1, y: 1, w: COLS, h: ROWS };
  return {
    position: "absolute" as const,
    left: share(p.x - 1, COLS),
    top: share(p.y - 1, ROWS),
    width: share(p.w, COLS),
    height: share(p.h, ROWS),
  };
}

/** Each column padded to its widest cell, so a table reads as columns. */
function tableCells(columns: string[], rows: string[][]): string[][] {
  const count = rows.reduce((max, row) => Math.max(max, row.length), columns.length);
  const widths = Array.from({ length: count }, (_, i) =>
    rows.reduce((max, row) => Math.max(max, (row[i] ?? "").length), (columns[i] ?? "").length),
  );
  const pad = (cells: string[]) => widths.map((width, i) => (cells[i] ?? "").padEnd(width));
  return [...(columns.length ? [pad(columns)] : []), ...rows.map(pad)];
}

/** Lines never shrink: a body taller than its pane is clipped at the bottom, not drawn over itself. */
function Blocks({ body, ink }: { body: PaneBody; ink: string }) {
  return (
    <box flexGrow={1} flexDirection="column" overflow="hidden">
      {body.blocks.map((block, index) => {
        switch (block.kind) {
          case "sentence":
            return (
              <text key={index} fg={ink} flexShrink={0}>
                {block.text}
              </text>
            );
          case "stat":
            return <StatLine key={index} text={block.text} />;
          case "chart":
            return (
              <text key={index} fg={ink} flexShrink={0}>
                {block.text}
              </text>
            );
          case "table":
            return (
              <box key={index} flexDirection="column" flexShrink={0}>
                {tableCells(block.columns, block.rows).map((cells, rowIndex) => (
                  <Toned key={rowIndex} cells={cells} sep="  " ink={rowIndex === 0 && block.columns.length ? MUTE : ink} />
                ))}
              </box>
            );
          default: {
            const exhaustive: never = block;
            return (
              <text key={index} fg={ink}>
                {String(exhaustive)}
              </text>
            );
          }
        }
      })}
    </box>
  );
}

/** Body cells, less the one-column padding each side. Null until laid out. */
type Fit = { chars: number; rows: number } | null;

/** One-row header, body, footer. Status on the left, the focus hint on the right.
 *  Closed, the body is the key view: the columns and rows that fit, the recent
 *  end of each chart. Open, it is everything. */
export function PaneFrame({
  title,
  status,
  focused,
  open = false,
  lines,
  blocks,
  ink,
}: {
  title: string;
  status: string;
  focused: boolean;
  open?: boolean;
  lines?: string[];
  blocks?: PaneBody;
  ink: string;
}) {
  const full = tidyBody(blocks ?? shapeLines(lines ?? []));
  const [fit, setFit] = useState<Fit>(null);
  const face = open || fit === null ? { body: full, hidden: null } : compactBody(full, fit);
  const body = face.body;
  const more = face.hidden ? hiddenLabel(face.hidden) : null;
  const measure = function (this: BoxRenderable) {
    const chars = Math.max(1, this.width - 2);
    const rows = Math.max(1, this.height - 1);
    setFit((prev) => (prev && prev.chars === chars && prev.rows === rows ? prev : { chars, rows }));
  };
  return (
    <box
      width="100%"
      height="100%"
      border
      borderColor={focused ? ACCENT : HAIR}
      flexDirection="column"
      overflow="hidden"
      backgroundColor={BG}
    >
      <box height={1} paddingLeft={1} paddingRight={1} border={["bottom"]} borderColor={HAIR} flexDirection="row" flexShrink={0}>
        <text fg={focused ? ACCENT : MUTE}>{title}</text>
        <box flexGrow={1} />
        {/* The header row shares its line with the rule, so the hint paints its own background. */}
        {focused ? (
          <text fg={MUTE} bg={BG}>
            {open ? CLOSE_HINT : OPEN_HINT}
          </text>
        ) : null}
      </box>
      <box flexGrow={1} paddingLeft={1} paddingRight={1} overflow="hidden" flexDirection="column" onSizeChange={measure}>
        <Blocks body={body} ink={ink} />
      </box>
      {/* Two rows, not one: a box that carries a top border spends its first
          row on that rule, so `height={1}` left the status with no content row
          at all and every page in this client drew a blank footer. One row for
          the rule, one for the words. */}
      <box height={2} paddingLeft={1} paddingRight={1} border={["top"]} borderColor={HAIR} flexDirection="row" flexShrink={0}>
        <text fg={MUTE}>{more ? `${status} · ${more}` : status}</text>
        <box flexGrow={1} />
        {focused ? <text fg={MUTE}>{PANE_HINT}</text> : null}
      </box>
    </box>
  );
}
