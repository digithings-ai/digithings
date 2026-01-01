"use client";

import { useEffect, useState } from "react";
import { useAuiState } from "@assistant-ui/react";
import { workStatusText } from "../gallery-thread/work-status";
import { useTraceT } from "../trace-i18n";
import { turnCutShort, useTurnOutcome, type TurnOutcome } from "../turn-outcome";
import { CHAIN_SETTLE_MS, chainOpen } from "./chain-state";

/** The header marker: what the chain is doing, or how it ended. */
export type WorkChainMarker = "loading" | "idle" | "error" | "stop";

export type WorkChainOptions = {
  /**
   * The message-part indices this chain holds. The folded header describes
   * them ("Working — digisearch", "Used 3 tools"); without them the header
   * keeps the plain title.
   */
  indices?: readonly number[] | undefined;
  /** Nothing ever folds (the verbose level). */
  openAtRest?: boolean | undefined;
  /** Fold as soon as the answer starts, not when the work settles (quiet). */
  foldOnAnswer?: boolean | undefined;
  /** A text part follows this chain: its work is over. */
  followedByText?: boolean | undefined;
};

export type WorkChainState = {
  open: boolean;
  onOpenChange: (open: boolean) => void;
  /** The header text. */
  title: string;
  marker: WorkChainMarker;
  /** `running`, `done`, or how a cut-short turn ended. */
  outcome: "running" | "done" | Exclude<TurnOutcome, "running" | "done">;
};

/**
 * The whole chain of reasoning and tool calls under one header: when it is
 * open, what the header says and which marker it shows.
 *
 * The header stays open for the whole run of work (not only while a group
 * happens to be running) so the block never flickers shut between two tool
 * calls, and folds `CHAIN_SETTLE_MS` after the answer starts. Folded, the
 * header is a live status line ("Working — web_search", "Used 3 tools");
 * open, it is the plain "Working" / "Worked" title, because the rows are
 * right underneath. The first manual toggle wins.
 *
 * A turn that was stopped or failed before any text is over too: the marker
 * stops and the title says how it ended.
 */
export function useWorkChain({
  indices,
  openAtRest = false,
  foldOnAnswer = false,
  followedByText = false,
}: WorkChainOptions): WorkChainState {
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const [settled, setSettled] = useState(false);

  const outcome = useTurnOutcome();
  const cutShort = !followedByText && turnCutShort(outcome);
  const working = !followedByText && !cutShort;

  useEffect(() => {
    if (working) {
      setSettled(false);
      return;
    }
    const id = setTimeout(() => setSettled(true), CHAIN_SETTLE_MS);
    return () => clearTimeout(id);
  }, [working]);

  const open = chainOpen({ userOpen, openAtRest, foldOnAnswer, working, settled });

  const parts = useAuiState((s) => s.message.parts);
  const tr = useTraceT();
  const status = !open && indices ? workStatusText(parts, indices, tr) : undefined;
  const endedTitle = outcome === "failed" ? tr.t("failed") : tr.t("stopped");
  const title = cutShort
    ? endedTitle
    : status
      ? status.label
      : working
        ? tr.t("working")
        : tr.t("worked");
  const markerRunning = !cutShort && (status ? status.running : working);
  const marker: WorkChainMarker = cutShort
    ? outcome === "failed"
      ? "error"
      : "stop"
    : markerRunning
      ? "loading"
      : "idle";

  return {
    open,
    onOpenChange: setUserOpen,
    title,
    marker,
    outcome: cutShort ? (outcome as "stopped" | "failed") : working ? "running" : "done",
  };
}
