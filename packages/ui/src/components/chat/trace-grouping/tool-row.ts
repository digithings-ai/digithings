/**
 * What a tool-call row says about its call, shared by every first-party
 * trace so the digichat skin and the base skins word a row the same way.
 * Pure: no React, callable from a test with plain objects.
 */
import type { ToolCallMessagePartStatus } from "@assistant-ui/react";
import { EN_TRACE_T, type TraceT } from "../trace-i18n/core";
import type { TurnOutcome } from "../turn-outcome";

/**
 * assistant-ui's `toMessagePartStatus` returns `{ type: "complete" }` for any
 * tool-call part with a defined `result` — even when `isError` is set, because
 * an `output-error` part carries `result = { error }`. Derive the error state
 * from `isError` so a failed or orphaned row does not render as success.
 */
export function resolveToolStatus(
  status: ToolCallMessagePartStatus | undefined,
  isError: boolean | undefined,
  result: unknown,
): ToolCallMessagePartStatus | undefined {
  if (!isError || status?.type === "incomplete") return status;
  const error =
    result && typeof result === "object" && "error" in result
      ? (result as { error?: unknown }).error
      : undefined;
  return { type: "incomplete", reason: "error", error };
}

/**
 * A call still waiting on a result when the turn was stopped will never get
 * one: it reads cancelled, not "Waiting on tool". A call that waits on the
 * visitor (approval, interrupt) keeps its controls.
 */
export function effectiveToolStatus(
  resolved: ToolCallMessagePartStatus | undefined,
  outcome: TurnOutcome,
  offersVisitorAction: boolean,
): ToolCallMessagePartStatus | undefined {
  return outcome === "stopped" &&
    resolved?.type === "requires-action" &&
    !offersVisitorAction
    ? { type: "incomplete", reason: "cancelled" }
    : resolved;
}

export type ToolRowStatus = {
  label: string;
  statusType: ToolCallMessagePartStatus["type"];
  isRunning: boolean;
  isCancelled: boolean;
  isError: boolean;
};

/** The row's words for a tool status: one word per state, upstream wording. */
export function toolRowStatus(
  status: ToolCallMessagePartStatus | undefined,
  tr: TraceT = EN_TRACE_T,
): ToolRowStatus {
  const statusType = status?.type ?? "complete";
  const isRunning = statusType === "running";
  const isCancelled =
    status?.type === "incomplete" && status.reason === "cancelled";
  const isError = status?.type === "incomplete" && status.reason === "error";
  const label = isCancelled
    ? tr.t("cancelledTool")
    : isError
      ? tr.t("failedTool")
      : statusType === "running"
        ? tr.t("runningTool")
        : statusType === "requires-action"
          ? tr.t("waitingOnTool")
          : tr.t("usedTool");
  return { label, statusType, isRunning, isCancelled, isError };
}
