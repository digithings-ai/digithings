"use client";

import { useAuiState, useMessageTiming } from "@assistant-ui/react";
import {
  Tooltip,
  TooltipContent,
  TooltipProvider,
  TooltipTrigger,
} from "./ui/tooltip";
import { cn } from "./cn";
import { formatToolDurationMs } from "./format-json-dump";
import type { FC } from "react";

const formatTokens = (count: number): string => count.toLocaleString("en-US");

type ThreadTokenUsage = {
  inputTokens?: number;
  outputTokens?: number;
  totalTokens?: number;
  reasoningTokens?: number;
  cachedInputTokens?: number;
};

const readTokenUsage = (value: unknown): ThreadTokenUsage | undefined => {
  if (typeof value !== "object" || value === null) return undefined;
  const record = value as Record<string, unknown>;
  const pick = (key: string): number | undefined =>
    typeof record[key] === "number" ? record[key] : undefined;
  const usage: ThreadTokenUsage = {
    inputTokens: pick("inputTokens"),
    outputTokens: pick("outputTokens"),
    totalTokens: pick("totalTokens"),
    reasoningTokens: pick("reasoningTokens"),
    cachedInputTokens: pick("cachedInputTokens"),
  };
  return Object.values(usage).some((tokens) => tokens !== undefined)
    ? usage
    : undefined;
};

const TimingRow: FC<{ label: string; value: string }> = ({ label, value }) => (
  <div className="flex items-center justify-between gap-4">
    <span className="text-muted-foreground">{label}</span>
    <span className="font-mono tabular-nums">{value}</span>
  </div>
);

export const MessageTiming: FC<{
  className?: string;
  side?: "top" | "right" | "bottom" | "left";
}> = ({ className, side = "right" }) => {
  const timing = useMessageTiming();
  const usage = readTokenUsage(
    useAuiState((s) => s.message.metadata.custom.usage),
  );

  if (timing?.totalStreamTime === undefined) return null;

  return (
    <TooltipProvider>
      <Tooltip>
        <TooltipTrigger asChild>
          <button
            type="button"
            data-slot="message-timing-trigger"
            aria-label="Message timing"
            className={cn(
              "text-muted-foreground hover:bg-accent hover:text-accent-foreground flex items-center rounded-md p-1 font-mono text-xs tabular-nums transition-colors",
              className,
            )}
          >
            {formatToolDurationMs(timing.totalStreamTime)}
          </button>
        </TooltipTrigger>
        <TooltipContent
          side={side}
          sideOffset={8}
          className="bg-popover text-popover-foreground border px-3 py-2 [&_[data-slot=tooltip-arrow]]:hidden"
        >
          <div
            data-slot="message-timing-popover"
            className="grid min-w-35 gap-1.5 text-xs"
          >
            {timing.firstTokenTime !== undefined && (
              <TimingRow
                label="First token"
                value={formatToolDurationMs(timing.firstTokenTime)}
              />
            )}
            <TimingRow
              label="Total"
              value={formatToolDurationMs(timing.totalStreamTime)}
            />
            {timing.tokensPerSecond !== undefined && (
              <TimingRow
                label="Speed"
                value={`${timing.tokensPerSecond.toFixed(1)} tok/s`}
              />
            )}
            <TimingRow label="Chunks" value={String(timing.totalChunks)} />
            {usage && (
              <>
                <div className="bg-border my-0.5 h-px" />
                {usage.inputTokens !== undefined && (
                  <TimingRow
                    label="Input tokens"
                    value={formatTokens(usage.inputTokens)}
                  />
                )}
                {usage.outputTokens !== undefined && (
                  <TimingRow
                    label="Output tokens"
                    value={formatTokens(usage.outputTokens)}
                  />
                )}
                {usage.totalTokens !== undefined && (
                  <TimingRow
                    label="Total tokens"
                    value={formatTokens(usage.totalTokens)}
                  />
                )}
                {usage.reasoningTokens !== undefined && (
                  <TimingRow
                    label="Reasoning"
                    value={formatTokens(usage.reasoningTokens)}
                  />
                )}
                {usage.cachedInputTokens !== undefined && (
                  <TimingRow
                    label="Cached input"
                    value={formatTokens(usage.cachedInputTokens)}
                  />
                )}
              </>
            )}
          </div>
        </TooltipContent>
      </Tooltip>
    </TooltipProvider>
  );
};
