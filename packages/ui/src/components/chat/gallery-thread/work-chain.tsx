"use client";

import type { ReactNode } from "react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../../../ui/collapsible";
import { DisclosureChevron } from "../disclosure-chevron";
import { WorkStatusLead } from "../work-status-lead";
import { cn } from "./cn";
import { useWorkChain } from "../trace-grouping/use-work-chain";

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
 *
 * Folded, the header is a live status line: it names the tool that is
 * running, or counts what the chain did once it is done. Expanded, it goes
 * back to the plain "Working" / "Worked" title, because the reasoning and the
 * tool calls are right there underneath — the header no longer has to
 * describe them.
 */
export function WorkChain({
  children,
  indices,
  openAtRest = false,
  foldOnAnswer = false,
  followedByText = false,
  className,
}: {
  children: ReactNode;
  /**
   * The message-part indices this chain holds. The folded header describes
   * them ("Working — digisearch", "Used 3 tools"); without them the header
   * has nothing to describe and keeps the plain title.
   */
  indices?: readonly number[];
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
  /**
   * A text part follows this chain in the message: the agent wrote
   * something, so the work that came before it is finished. Only the answer
   * ends a work run — a second run of tool calls and reasoning without text
   * in between belongs to the same block.
   */
  followedByText?: boolean;
  className?: string;
}) {
  // The fold, the header title and the marker are the shared trace rules
  // (`trace-grouping`), which the base skins render too.
  const { open, onOpenChange, title, marker, outcome } = useWorkChain({
    indices,
    openAtRest,
    foldOnAnswer,
    followedByText,
  });

  return (
    <Collapsible
      data-slot="aui_work-chain"
      data-outcome={outcome}
      open={open}
      onOpenChange={onOpenChange}
      className={cn("aui-work-chain", className)}
      style={{ "--animation-duration": `${ANIMATION_DURATION}ms` } as React.CSSProperties}
    >
      <CollapsibleTrigger
        data-slot="aui_work-chain-trigger"
        className="aui-work-chain-trigger aui-work-status group/trigger"
      >
        {/* Same lead as the pre-response loader: the marker and the label
            keep their slots, so the handoff reads as the words changing. */}
        <WorkStatusLead marker={marker} label={title} />
        <DisclosureChevron />
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
