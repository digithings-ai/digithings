import { useKeyboard } from "@opentui/react";
import { useState } from "react";
import { toneOf } from "../format";
import { ACCENT, BG, DOWN, HAIR, MUTE, UP } from "../theme";
import { shapeLines, type PaneBody } from "./shape";

export const PANE_HINT = "[tab] next";

/** Tab moves the focused pane. A new reset key returns focus to the first pane. */
export function useFocusedPane(count: number, resetKey = ""): [number, (index: number) => void] {
  const [state, setState] = useState({ resetKey, focus: 0 });
  const focus = state.resetKey === resetKey ? state.focus : 0;
  useKeyboard((key) => {
    if ((key.name ?? "") !== "tab" || count <= 0) return;
    setState((current) => {
      const index = current.resetKey === resetKey && current.focus >= 0 && current.focus < count ? current.focus : 0;
      const next = key.shift ? (index - 1 + count) % count : (index + 1) % count;
      return { resetKey, focus: next };
    });
  });
  const shown = count <= 0 ? 0 : Math.min(focus, count - 1);
  return [shown, (index: number) => setState({ resetKey, focus: index })];
}

/** A signed figure is green or red; everything else keeps the pane ink. */
function toneInk(text: string, ink: string): string {
  const tone = toneOf(text);
  return tone === "up" ? UP : tone === "down" ? DOWN : ink;
}

/** One row of cells, `sep` between them, each cell in its own tone. */
function Toned({ cells, sep, ink }: { cells: string[]; sep: string; ink: string }) {
  return (
    <text fg={ink}>
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
    <text fg={MUTE}>
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

function Blocks({ body, ink }: { body: PaneBody; ink: string }) {
  return (
    <box flexGrow={1} flexDirection="column" overflow="hidden">
      {body.blocks.map((block, index) => {
        switch (block.kind) {
          case "sentence":
            return (
              <text key={index} fg={ink}>
                {block.text}
              </text>
            );
          case "stat":
            return <StatLine key={index} text={block.text} />;
          case "chart":
            return (
              <text key={index} fg={ink}>
                {block.text}
              </text>
            );
          case "table":
            return (
              <box key={index} flexDirection="column">
                {block.columns.length ? <text fg={MUTE}>{block.columns.join("  ")}</text> : null}
                {block.rows.map((row, rowIndex) => (
                  <Toned key={rowIndex} cells={row} sep="  " ink={ink} />
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

/** One-row header, body, footer. Status on the left, the focus hint on the right. */
export function PaneFrame({
  title,
  status,
  focused,
  lines,
  blocks,
  ink,
}: {
  title: string;
  status: string;
  focused: boolean;
  lines?: string[];
  blocks?: PaneBody;
  ink: string;
}) {
  const body = blocks ?? shapeLines(lines ?? []);
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
      <box height={1} paddingLeft={1} paddingRight={1} border={["bottom"]} borderColor={HAIR} flexShrink={0}>
        <text fg={focused ? ACCENT : MUTE}>{title}</text>
      </box>
      <box flexGrow={1} paddingLeft={1} paddingRight={1} overflow="hidden" flexDirection="column">
        <Blocks body={body} ink={ink} />
      </box>
      {/* Two rows, not one: a box that carries a top border spends its first
          row on that rule, so `height={1}` left the status with no content row
          at all and every page in this client drew a blank footer. One row for
          the rule, one for the words. */}
      <box height={2} paddingLeft={1} paddingRight={1} border={["top"]} borderColor={HAIR} flexDirection="row" flexShrink={0}>
        <text fg={MUTE}>{status}</text>
        <box flexGrow={1} />
        {focused ? <text fg={MUTE}>{PANE_HINT}</text> : null}
      </box>
    </box>
  );
}
