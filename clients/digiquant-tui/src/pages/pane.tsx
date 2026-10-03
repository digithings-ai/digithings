import { useKeyboard } from "@opentui/react";
import { useState } from "react";
import { shapeLines, type PaneBody } from "./shape";

const BG = "#14120f";
const DIM = "#8a8175";
const LINE = "#3a342c";
const GOLD = "#d4b483";

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

function Blocks({ body, ink }: { body: PaneBody; ink: string }) {
  return (
    <box flexGrow={1} flexDirection="column" overflow="hidden">
      {body.blocks.map((block, index) => {
        if (block.kind === "sentence") {
          return (
            <text key={index} fg={ink}>
              {block.text}
            </text>
          );
        }
        if (block.kind === "stat") {
          return (
            <text key={index} fg={DIM}>
              {block.text}
            </text>
          );
        }
        return (
          <box key={index} flexDirection="column">
            {block.columns.length ? <text fg={DIM}>{block.columns.join("  ")}</text> : null}
            {block.rows.map((row, rowIndex) => (
              <text key={rowIndex} fg={ink}>
                {row.join("  ")}
              </text>
            ))}
          </box>
        );
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
      borderColor={focused ? GOLD : LINE}
      flexDirection="column"
      overflow="hidden"
      backgroundColor={BG}
    >
      <box height={1} paddingLeft={1} paddingRight={1} border={["bottom"]} borderColor={LINE} flexShrink={0}>
        <text fg={focused ? GOLD : DIM}>{title}</text>
      </box>
      <box flexGrow={1} paddingLeft={1} paddingRight={1} overflow="hidden" flexDirection="column">
        <Blocks body={body} ink={ink} />
      </box>
      <box height={1} paddingLeft={1} paddingRight={1} border={["top"]} borderColor={LINE} flexDirection="row" flexShrink={0}>
        <text fg={DIM}>{status}</text>
        <box flexGrow={1} />
        {focused ? <text fg={DIM}>{PANE_HINT}</text> : null}
      </box>
    </box>
  );
}
