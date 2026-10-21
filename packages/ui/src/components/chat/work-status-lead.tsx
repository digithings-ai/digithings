"use client";

import type { ReactNode } from "react";
import { DotMatrix, type DotMatrixState } from "./DotMatrix";

/**
 * Marker and label shared by the pre-response loader and the Working / Worked
 * header. Both rows render this, so the handoff is the label changing in the
 * same slot beside the same 12px marker.
 */
export function WorkStatusLead({
  marker,
  markerLabel,
  label,
}: {
  marker: DotMatrixState;
  markerLabel: string;
  label?: ReactNode;
}) {
  const showLabel =
    label !== null &&
    label !== undefined &&
    !(typeof label === "string" && label.trim() === "");

  return (
    <>
      <span data-slot="aui_work-status-marker" className="aui-work-status-marker">
        <DotMatrix
          state={marker}
          label={markerLabel}
          className="!size-3 shrink-0"
        />
      </span>
      {showLabel ? (
        <span data-slot="aui_work-status-label" className="aui-work-status-label">
          {label}
        </span>
      ) : null}
    </>
  );
}
