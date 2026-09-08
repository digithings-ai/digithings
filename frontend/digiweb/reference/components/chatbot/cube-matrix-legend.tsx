import { DotMatrix, type DotMatrixState } from "@/components/ui/dot-matrix";

const SPECIMENS: readonly { state: DotMatrixState; caption: string }[] = [
  { state: "loading", caption: "loading" },
  { state: "thinking", caption: "thinking" },
  { state: "tool", caption: "tool" },
  { state: "executing", caption: "executing" },
  { state: "searching", caption: "search" },
  { state: "compacting", caption: "compacting" },
  { state: "warning", caption: "caution" },
  { state: "error", caption: "error" },
];

/** Agent-action patterns. Cubes snap on/off — no fade. */
export function CubeMatrixLegend() {
  return (
    <ul className="cube-matrix-legend">
      {SPECIMENS.map(({ state, caption }) => (
        <li key={state} className="cube-matrix-legend-item">
          <DotMatrix state={state} label={caption} />
          <span className="cube-matrix-legend-caption">{caption}</span>
        </li>
      ))}
    </ul>
  );
}
