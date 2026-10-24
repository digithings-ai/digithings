"use client";

import { useAuiState } from "@assistant-ui/react";
import { DotMatrix } from "../DotMatrix";
import { cn } from "./cn";
import { workStatusText } from "./work-status";

/**
 * The one line that replaces the whole chain.
 *
 * This is the retired "hidden" view level: the chain collapsed into a single
 * status row. The level is gone — a client folds the chain to its titles
 * instead — so nothing in the product renders this any more; the thread
 * renderer still holds the branch that would, and it draws from the same
 * `workStatusText` the chain header uses so the two can never disagree.
 */
export function WorkChainSummary({
  indices,
  className,
}: {
  indices: readonly number[];
  className?: string;
}) {
  const parts = useAuiState((s) => s.message.parts);
  const status = workStatusText(parts, indices);

  return (
    <div
      data-slot="aui_work-chain-summary"
      className={cn(
        "aui-work-chain-summary text-ink-mute flex items-center gap-2 py-1.5 text-sm",
        className,
      )}
    >
      <DotMatrix
        state={status.running ? "loading" : "success"}
        decorative
        className="size-4 shrink-0"
      />
      <span
        data-slot="aui_work-chain-summary-label"
        className="inline-block leading-none"
      >
        {status.label}
      </span>
    </div>
  );
}
