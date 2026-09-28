import { DotMatrix, type DotMatrixState } from "@/components/ui/dot-matrix";

const MOTION: readonly { state: DotMatrixState; caption: string }[] = [
  { state: "loading", caption: "loading" },
  { state: "thinking", caption: "thinking" },
  { state: "tool", caption: "tool" },
  { state: "executing", caption: "executing" },
  { state: "searching", caption: "search" },
  { state: "compacting", caption: "compacting" },
  { state: "thought", caption: "thought" },
  { state: "warning", caption: "caution" },
  { state: "error", caption: "error" },
  { state: "success", caption: "copied" },
];

const CHROME: readonly { state: DotMatrixState; caption: string }[] = [
  { state: "user", caption: "user" },
  { state: "assistant", caption: "assistant" },
  { state: "example", caption: "example" },
  { state: "system", caption: "system" },
  { state: "copy", caption: "copy" },
  { state: "edit", caption: "edit" },
  { state: "attach", caption: "attach" },
  { state: "send", caption: "send" },
  { state: "more", caption: "more" },
  { state: "refresh", caption: "redo" },
  { state: "newChat", caption: "new chat" },
  { state: "export", caption: "export" },
  { state: "download", caption: "download" },
  { state: "stop", caption: "stop" },
  { state: "remove", caption: "remove" },
  { state: "scroll", caption: "scroll" },
  { state: "up", caption: "up" },
  { state: "down", caption: "down" },
  { state: "prev", caption: "prev" },
  { state: "next", caption: "next" },
  { state: "dictate", caption: "dictate" },
  { state: "thumbsUp", caption: "thumbs up" },
  { state: "thumbsDown", caption: "thumbs down" },
  { state: "expand", caption: "expand" },
];

function LegendGroup({
  items,
}: {
  items: readonly { state: DotMatrixState; caption: string }[];
}) {
  return (
    <ul className="cube-matrix-legend">
      {items.map(({ state, caption }) => (
        <li key={state} className="cube-matrix-legend-item">
          <DotMatrix state={state} label={caption} />
          <span className="cube-matrix-legend-caption">{caption}</span>
        </li>
      ))}
    </ul>
  );
}

/** Agent-action and chrome patterns. Cubes snap on/off — no fade. */
export function CubeMatrixLegend() {
  return (
    <div className="cube-matrix-legend-groups">
      <LegendGroup items={MOTION} />
      <LegendGroup items={CHROME} />
    </div>
  );
}
