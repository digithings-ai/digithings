"use client";

import type { FC } from "react";
import { DotMatrix, type DotMatrixState } from "../DotMatrix";
import { toolRowTitle } from "../stock/tool-display";
import { cn } from "./cn";

/**
 * One work step in a private session: that it happened, what kind of step it
 * was, and whether it finished. Not a disclosure — there is no trigger, no
 * chevron and no body, because in a private session the server never sends
 * the arguments, results or reasoning text a body would show
 * (apps/digichat/src/lib/private-stream.ts).
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
};

export function privateWorkStepLabel({
  kind,
  statusType,
  reason,
  isError,
}: Pick<PrivateWorkStepProps, "kind" | "statusType" | "reason" | "isError">): {
  label: string;
  state: DotMatrixState;
} {
  const running = statusType === "running";
  if (kind === "reasoning") {
    return running
      ? { label: "Thinking", state: "tool" }
      : { label: "Thought", state: "success" };
  }
  if (statusType === "incomplete" && reason === "cancelled") {
    return { label: "Cancelled tool", state: "idle" };
  }
  if (isError || (statusType === "incomplete" && reason !== "cancelled")) {
    return { label: "Failed tool", state: "error" };
  }
  if (running) return { label: "Running tool", state: "tool" };
  if (statusType === "requires-action") return { label: "Waiting on tool", state: "warning" };
  return { label: "Used tool", state: "success" };
}

export const PrivateWorkStep: FC<PrivateWorkStepProps> = ({
  kind,
  toolName,
  statusType,
  reason,
  isError,
}) => {
  const { label, state } = privateWorkStepLabel({ kind, statusType, reason, isError });
  const running = statusType === "running";
  const name = kind === "tool" ? toolRowTitle(toolName ?? "") : null;
  return (
    <div
      data-slot="aui_private-work-step"
      data-kind={kind}
      data-state={state}
      className="aui-private-work-step text-ink-mute flex w-fit items-center gap-2 py-1.5 text-sm select-none"
    >
      <DotMatrix state={state} decorative className="size-4 shrink-0" />
      <span
        className={cn(
          "inline-block text-start leading-none text-ink",
          state === "idle" && "text-ink-mute line-through",
          running && "shimmer motion-reduce:animate-none",
        )}
      >
        {name ? (
          <>
            {label}: <b>{name}</b>
          </>
        ) : (
          label
        )}
      </span>
    </div>
  );
};
