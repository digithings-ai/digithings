"use client";

import { useAuiState } from "@assistant-ui/react";

/**
 * How the current assistant turn stands, for the animations that follow it.
 *
 * - `running`: the turn is live, or waiting on the visitor (a tool approval).
 * - `done`: the turn finished.
 * - `stopped`: the visitor pressed stop, or the stream ended with a tool call
 *   still open. Nothing more will arrive for it.
 * - `failed`: the turn ended on an error.
 *
 * A stopped or failed turn ends every animation it started: the work-chain
 * marker, its "Working" title and the open tool rows all show their final
 * state instead (DIG-4459).
 */
export type TurnOutcome = "running" | "done" | "stopped" | "failed";

type StatusLike = { readonly type?: string; readonly reason?: string } | null | undefined;

/**
 * assistant-ui's message status after the stream ends:
 * - an error is `incomplete/error`;
 * - a stop is `incomplete/cancelled`, except while a tool call has no result,
 *   when it is `requires-action/tool-calls` (getAutoStatus ranks pending tool
 *   calls above the cancel). Our tools run on the server, so a pending call
 *   with the thread idle is a call that will never finish.
 * - `requires-action/interrupt` waits on the visitor and stays live.
 */
export function turnOutcome(status: StatusLike, threadRunning: boolean): TurnOutcome {
  const type = status?.type;
  if (type === "incomplete") return status?.reason === "error" ? "failed" : "stopped";
  if (type === "requires-action") {
    return status?.reason === "tool-calls" && !threadRunning ? "stopped" : "running";
  }
  if (type === "running") return "running";
  return "done";
}

/** The outcome of the message in scope; `done` outside a message. */
export function useTurnOutcome(): TurnOutcome {
  const status = useAuiState((s) => s.optional.message?.status as StatusLike);
  const threadRunning = useAuiState((s) => s.optional.thread?.isRunning === true);
  if (status === undefined) return "done";
  return turnOutcome(status, threadRunning);
}

/** A turn that ended before it finished: stopped by the visitor or failed. */
export function turnCutShort(outcome: TurnOutcome): boolean {
  return outcome === "stopped" || outcome === "failed";
}
