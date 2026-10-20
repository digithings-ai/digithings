"use client";

import { useAuiState } from "@assistant-ui/react";
import { DotMatrix } from "../DotMatrix";
import { cn } from "./cn";

/**
 * The one line a quiet client sees instead of the whole chain.
 *
 * While the agent is working it names what is running ("Working — digisearch");
 * once the chain is done it counts what it did ("Used 3 tools"). The reasoning
 * and the tool calls themselves stay closed — that is the point of the quiet
 * level.
 */
export function WorkChainSummary({
  indices,
  className,
}: {
  indices: readonly number[];
  className?: string;
}) {
  const parts = useAuiState((s) => s.message.parts);

  const chain = indices
    .map((index) => parts[index])
    .filter((part): part is NonNullable<typeof part> => Boolean(part));
  const tools = chain.filter(
    (part) => part.type === "tool-call" && "toolName" in part,
  );
  const running = tools.find(
    (part) => "status" in part && part.status?.type === "running",
  );
  const thinking = chain.some(
    (part) =>
      part.type === "reasoning" &&
      "status" in part &&
      part.status?.type === "running",
  );

  const label = running
    ? `Working — ${"toolName" in running ? running.toolName : "tool"}`
    : thinking
      ? "Thinking"
      : tools.length > 0
        ? `Used ${tools.length} tool${tools.length === 1 ? "" : "s"}`
        : "Thought";

  return (
    <div
      data-slot="aui_work-chain-summary"
      className={cn(
        "aui-work-chain-summary text-muted-foreground flex items-center gap-2 py-1.5 text-sm",
        className,
      )}
    >
      <DotMatrix
        state={running || thinking ? "loading" : "success"}
        label={label}
        className="size-4 shrink-0"
      />
      <span
        data-slot="aui_work-chain-summary-label"
        className="inline-block leading-none"
      >
        {label}
      </span>
    </div>
  );
}
