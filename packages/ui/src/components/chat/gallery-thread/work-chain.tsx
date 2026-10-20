"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useAuiState } from "@assistant-ui/react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../../../ui/collapsible";
import { DotMatrix } from "../DotMatrix";
import { cn } from "./cn";

/**
 * How long the chain waits before it folds away once the turn is over.
 *
 * The tools answer faster than the eye can follow: without this the block
 * shuts between two tool calls and opens again, which reads as a glitch.
 */
const SETTLE_MS = 600;

/** The upstream disclosure duration. */
const ANIMATION_DURATION = 200;

/**
 * The whole chain of reasoning and tool calls under one header.
 *
 * assistant-ui keeps the reasoning disclosure and the tool-group disclosure
 * independent. We put them under a single "Working" header so the chain
 * collapses as one unit, and the header stays open for the whole turn (not
 * only while a group happens to be running) so the block never flickers shut
 * between two tool calls.
 *
 * The first manual toggle wins, as it does upstream.
 */
export function WorkChain({
  children,
  openAtRest = false,
  foldOnAnswer = false,
  running = false,
  className,
}: {
  children: ReactNode;
  /**
   * The chain stays open for good: nothing ever folds (the verbose level).
   * The balanced level instead opens the chain while the turn runs and folds
   * it away when the turn ends.
   */
  openAtRest?: boolean;
  /**
   * Fold as soon as the answer starts streaming, rather than when the turn
   * ends (the quiet level: the titles are there while the agent works, then
   * they get out of the way of the answer).
   */
  foldOnAnswer?: boolean;
  /** The chain group is running (a tool or the reasoning is streaming). */
  running?: boolean;
  className?: string;
}) {
  const turnRunning = useAuiState((s) => s.thread.isRunning);
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const [settled, setSettled] = useState(false);

  useEffect(() => {
    if (running || turnRunning) {
      setSettled(false);
      return;
    }
    const id = setTimeout(() => setSettled(true), SETTLE_MS);
    return () => clearTimeout(id);
  }, [running, turnRunning]);

  // The answer has started: the text part of this message carries content.
  const answerStarted = useAuiState((s) =>
    s.message.parts.some(
      (part) =>
        part.type === "text" &&
        typeof (part as { text?: string }).text === "string" &&
        (part as { text?: string }).text !== "",
    ),
  );

  const busy = running || turnRunning;
  const open = userOpen ?? (
    openAtRest
      ? true
      : foldOnAnswer
        ? busy && !answerStarted
        : !settled && busy
  );

  return (
    <Collapsible
      data-slot="aui_work-chain"
      open={open}
      onOpenChange={setUserOpen}
      className={cn("aui-work-chain", className)}
      style={{ "--animation-duration": `${ANIMATION_DURATION}ms` } as React.CSSProperties}
    >
      <CollapsibleTrigger
        data-slot="aui_work-chain-trigger"
        className="aui-work-chain-trigger group/trigger text-muted-foreground hover:text-foreground flex w-fit origin-left items-center gap-2 py-1.5 text-xs transition-[color,scale] active:scale-[0.98]"
      >
        {/* The marker is always there: the loading trail while the work runs,
            the quiet corner dots when it is done. The slot keeps its size, so
            the title never shifts when the turn ends — and the check mark
            stays where it belongs, on the tool rows. */}
        <DotMatrix
          state={busy ? "loading" : "idle"}
          label={busy ? "Working" : "Worked"}
          className="!size-3 shrink-0"
        />
        <span
          data-slot="aui_work-chain-label"
          className="aui-work-chain-label inline-block leading-none"
        >
          {busy ? "Working" : "Worked"}
        </span>
        <span
          data-slot="aui_work-chain-chevron"
          className="aui-work-chain-chevron inline-flex shrink-0"
        >
          <DotMatrix
            state="expand"
            label="Toggle the work"
            className="size-3 shrink-0"
          />
        </span>
      </CollapsibleTrigger>
      <CollapsibleContent
        // Kept mounted: the rows inside keep their own state (and the DOM
        // stays stable) while the chain is folded away.
        keepMounted
        data-slot="aui_work-chain-content"
        className="aui-work-chain-content overflow-hidden ease-[cubic-bezier(0.32,0.72,0,1)] motion-reduce:animate-none data-closed:animate-collapsible-up data-open:animate-collapsible-down data-closed:fill-mode-forwards data-closed:pointer-events-none [--tw-duration:var(--animation-duration)]"
      >
        {children}
      </CollapsibleContent>
    </Collapsible>
  );
}
