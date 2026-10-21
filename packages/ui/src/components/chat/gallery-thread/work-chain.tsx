"use client";

import { useEffect, useState, type ReactNode } from "react";
import { useAuiState } from "@assistant-ui/react";
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from "../../../ui/collapsible";
import { DisclosureChevron } from "../disclosure-chevron";
import { WorkStatusLead } from "../work-status-lead";
import { cn } from "./cn";
import { workStatusText } from "./work-status";

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
  running = false,
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
  const [userOpen, setUserOpen] = useState<boolean | null>(null);
  const [settled, setSettled] = useState(false);

  // The work of this block is over when text follows it: the agent wrote
  // something, so it stopped reasoning and stopped calling tools for that
  // run. Until then the block is still working — a second run of tool calls
  // and reasoning without text in between is the same block, not a new one.
  // The marker and the title follow the work; the disclosure follows it too.
  const working = !followedByText;

  useEffect(() => {
    if (working) {
      setSettled(false);
      return;
    }
    const id = setTimeout(() => setSettled(true), SETTLE_MS);
    return () => clearTimeout(id);
  }, [working]);

  const open = userOpen ?? (
    openAtRest ? true : foldOnAnswer ? working : !settled && working
  );

  // Folded, the header is a live status line — the same sentence the retired
  // summary level showed. Expanded, the plain title is enough: the reasoning
  // and the tool calls are underneath it.
  const parts = useAuiState((s) => s.message.parts);
  const status = !open && indices ? workStatusText(parts, indices) : undefined;
  const title = status ? status.label : working ? "Working" : "Worked";
  const markerRunning = status ? status.running : working;

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
        className="aui-work-chain-trigger aui-work-status group/trigger"
      >
        {/* Same lead as the pre-response loader: the marker and the label
            keep their slots, so the handoff reads as the words changing. */}
        <WorkStatusLead
          marker={markerRunning ? "loading" : "idle"}
          markerLabel={title}
          label={title}
        />
        <DisclosureChevron label="Toggle the work" />
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
