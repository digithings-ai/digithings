"use client";

import type { FC, ReactNode } from "react";
import type { ToolCallMessagePartStatus } from "@assistant-ui/react";
import { DotMatrix } from "../DotMatrix";
import { toolRowTitle } from "../stock/tool-display";
import {
  resolveToolStatus,
  ToolFallbackDuration,
  toolTriggerLabel,
} from "../stock/tool-fallback.aui";
import { useTurnOutcome } from "../turn-outcome";
import { cn } from "./cn";

/**
 * One work step in a private session, drawn exactly like the normal row —
 * the same slots, classes, icon, wording and running/done state, so the skin
 * styles it the same — but it is not a disclosure. There is no button, no
 * chevron, no body and no hover change: in a private session the server
 * never sends the arguments, results or reasoning text a body would show
 * (apps/digichat/src/lib/private-stream.ts), so the row has nothing to open.
 *
 * `pointer-events: none` keeps the skin's `:hover` / `:active` rules off it
 * and makes a click on the row land on nothing.
 */
export type PrivateWorkStepProps = {
  kind: "tool" | "reasoning";
  /** Tool name for a tool step; ignored for reasoning. */
  toolName?: string;
  /** assistant-ui part status type: running | complete | incomplete | requires-action. */
  statusType?: string;
  /** incomplete reason: error | cancelled | … */
  reason?: string;
  isError?: boolean;
  /** Trailing meta on a tool row (the elapsed time), same as the normal row. */
  trailing?: ReactNode;
};

/** A failed call reads as failed even when its part says complete (see `resolveToolStatus`). */
function toolStatus(
  statusType: string | undefined,
  reason: string | undefined,
  isError: boolean | undefined,
): ToolCallMessagePartStatus | undefined {
  if (isError && statusType !== "incomplete") {
    return { type: "incomplete", reason: "error" } as ToolCallMessagePartStatus;
  }
  if (!statusType) return undefined;
  return { type: statusType, ...(reason ? { reason } : {}) } as ToolCallMessagePartStatus;
}

/** The normal rows' words: "Reasoning" for a reasoning row, the upstream tool wording for a tool row. */
export function privateWorkStepLabel({
  kind,
  statusType,
  reason,
  isError,
}: Pick<PrivateWorkStepProps, "kind" | "statusType" | "reason" | "isError">): {
  label: string;
  state: string;
} {
  const running = statusType === "running";
  if (kind === "reasoning") {
    return { label: "Reasoning", state: running ? "thinking" : "thought" };
  }
  const { label, matrixState } = toolTriggerLabel(toolStatus(statusType, reason, isError));
  return { label, state: matrixState };
}

const INERT = "pointer-events-none cursor-default select-none";

export const PrivateWorkStep: FC<PrivateWorkStepProps> = ({
  kind,
  toolName,
  statusType,
  reason,
  isError,
  trailing,
}) => {
  const running = statusType === "running";
  if (kind === "reasoning") {
    return (
      <div
        data-slot="aui_private-work-step"
        data-kind="reasoning"
        data-state={running ? "thinking" : "thought"}
        className="aui-reasoning-root w-full"
      >
        <div
          data-slot="reasoning-trigger"
          data-private=""
          className={cn(
            "aui-reasoning-trigger text-ink-mute flex w-full items-center gap-2 py-1.5 text-sm",
            INERT,
          )}
        >
          <span
            data-slot="reasoning-trigger-icon"
            className="aui-reasoning-trigger-icon inline-flex size-3.5 shrink-0 items-center justify-center"
          >
            <DotMatrix state={running ? "thinking" : "thought"} decorative className="size-3.5" />
          </span>
          <span
            data-slot="reasoning-trigger-label"
            className={cn(
              "aui-reasoning-trigger-label-wrapper min-w-0 flex-1 truncate text-start leading-none tabular-nums",
              running && "shimmer motion-reduce:animate-none",
            )}
          >
            Reasoning
          </span>
        </div>
      </div>
    );
  }
  const { label, matrixState, isRunning, isCancelled } = toolTriggerLabel(
    toolStatus(statusType, reason, isError),
  );
  return (
    <div
      data-slot="aui_private-work-step"
      data-kind="tool"
      data-state={matrixState}
      className="aui-tool-fallback-root w-full"
    >
      <div
        data-slot="tool-fallback-trigger"
        data-private=""
        className={cn(
          "aui-tool-fallback-trigger text-ink-mute flex w-fit origin-left items-center gap-2 py-1.5 text-sm",
          INERT,
        )}
      >
        <DotMatrix
          state={matrixState}
          decorative
          className="aui-tool-fallback-trigger-icon size-4 shrink-0"
        />
        <span
          data-slot="tool-fallback-trigger-label"
          className={cn(
            "aui-tool-fallback-trigger-label-wrapper inline-block text-start leading-none text-ink",
            isCancelled && "text-ink-mute line-through",
            isRunning && "shimmer motion-reduce:animate-none",
          )}
        >
          {label}: <b>{toolRowTitle(toolName ?? "")}</b>
        </span>
        {trailing}
      </div>
    </div>
  );
};

/**
 * A tool-call part in a private session, with the status rules of the normal
 * row (`ToolFallback`): a failed call reads as failed, a call left waiting
 * when the turn was stopped reads as cancelled, and the elapsed time trails
 * the label. Never the part's custom renderer and never a body.
 */
export const PrivateToolCallStep: FC<{
  toolName: string;
  status?: ToolCallMessagePartStatus | undefined;
  isError?: boolean | undefined;
  result?: unknown;
}> = ({ toolName, status, isError, result }) => {
  const outcome = useTurnOutcome();
  const resolved = resolveToolStatus(status, isError, result);
  const effective =
    outcome === "stopped" && resolved?.type === "requires-action"
      ? ({ type: "incomplete", reason: "cancelled" } as const)
      : resolved;
  return (
    <PrivateWorkStep
      kind="tool"
      toolName={toolName}
      statusType={effective?.type}
      reason={(effective as { reason?: string } | undefined)?.reason}
      trailing={<ToolFallbackDuration />}
    />
  );
};
