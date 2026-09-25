/**
 * Module pipeline strip, diagram + full-card stage list (#4429).
 *
 * The mosaic's focused tile shows exactly what it always showed (facts,
 * lead paragraph, stack, foot). The pipeline lives in the click-expanded
 * card: `ModuleFlowDiagram` (an SVG node chain with flowing connectors),
 * `ModuleFlowStrip` (the mono stage labels), and `ModuleStageList` (the
 * stage-by-stage tour). No dialog anywhere — the card grows in place.
 *
 * No global CSS beyond `m-flow*`: classes live in styles/flow.css, imported
 * by the app's globals. The diagram's dash flow freezes under
 * `prefers-reduced-motion: reduce`, per kit convention.
 */
"use client";

import { cn } from "../../lib/utils";

export interface FlowStage {
  label: string;
  detail: string;
}

export interface ModuleFlowStripProps {
  stages: FlowStage[];
  className?: string;
}

/** Compact pipeline strip for the focused mosaic tile. */
export function ModuleFlowStrip({ stages, className }: ModuleFlowStripProps) {
  return (
    <ol className={cn("m-flow", className)} aria-label="Module pipeline" data-flow>
      {stages.map((stage, i) => (
        <li key={stage.label} className="m-flow-item">
          {i > 0 ? (
            <span className="m-flow-arrow" aria-hidden="true">
              →
            </span>
          ) : null}
          <span className="m-flow-stage">{stage.label}</span>
        </li>
      ))}
    </ol>
  );
}

export interface ModuleStageListProps {
  stages: FlowStage[];
  className?: string;
}

/** Stage-by-stage tour cards for the expanded full module card. */
export function ModuleStageList({ stages, className }: ModuleStageListProps) {
  return (
    <ol className={cn("m-stages", className)} aria-label="Module pipeline, stage by stage">
      {stages.map((stage, i) => (
        <li key={stage.label} className="m-stage">
          <span className="m-stage-num" aria-hidden="true">
            {String(i + 1).padStart(2, "0")}
          </span>
          <div>
            <p className="m-stage-label">{stage.label}</p>
            <p className="m-stage-detail">{stage.detail}</p>
          </div>
        </li>
      ))}
    </ol>
  );
}

export interface ModuleFlowDiagramProps {
  stages: FlowStage[];
  /** Module id, for the accessible name (e.g. "digiquant"). */
  label: string;
  className?: string;
}

/**
 * Pipeline node chain for the top of the expanded card: one node per stage,
 * flowing connectors between them. Pure SVG + one CSS dash animation (frozen
 * under reduced motion); `role="img"` with the full stage order in the name
 * so AT gets the same journey sighted readers do.
 */
export function ModuleFlowDiagram({ stages, label, className }: ModuleFlowDiagramProps) {
  const step = 150;
  const width = Math.max(stages.length * step, step);
  const cx = (i: number) => i * step + step / 2;
  return (
    <svg
      className={cn("m-flowdiag", className)}
      viewBox={`0 0 ${width} 64`}
      role="img"
      aria-label={`${label} pipeline: ${stages.map((s) => s.label).join(" to ")}`}
    >
      {stages.slice(1).map((_, i) => (
        <line
          key={`c${i}`}
          className="m-flowdiag-dash"
          x1={cx(i) + 8}
          y1={20}
          x2={cx(i + 1) - 8}
          y2={20}
        />
      ))}
      {stages.map((stage, i) => (
        <g key={stage.label}>
          <circle className="m-flowdiag-node" cx={cx(i)} cy={20} r={5} />
          <text className="m-flowdiag-label" x={cx(i)} y={44} textAnchor="middle">
            {stage.label}
          </text>
        </g>
      ))}
    </svg>
  );
}
