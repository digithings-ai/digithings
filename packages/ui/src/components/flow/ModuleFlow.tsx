/**
 * Module pipeline strip + full-card stage list (#4429).
 *
 * The mosaic's focused tile shows the pipeline, not the prose: a mono strip
 * of stage labels joined by arrows (`ModuleFlowStrip`, marked `data-flow`
 * for tests and probes). Clicking the tile's Expand control opens the
 * complete module card as an in-flow panel below the mosaic
 * (`ModuleStageList` renders the stage-by-stage tour inside it) — the mosaic
 * section takes the room the full card needs, no dialog, no compact-only
 * view. The app owns the panel chrome (header, meta, foot); the kit owns
 * the strip and the stage list.
 *
 * No global CSS beyond `m-flow*`: classes live in styles/flow.css, imported
 * by the app's globals. No animation here — motion belongs to the mosaic
 * pin, not the card.
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
