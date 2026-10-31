"use client";

import { useRef, type ReactNode } from "react";
import { useScrollLock } from "@assistant-ui/react";
import {
  ChevronRightIcon,
  CircleAlertIcon,
  CircleStopIcon,
  LoaderIcon,
} from "lucide-react";
import { cn } from "@/lib/utils";
import {
  CollapsibleContent,
  CollapsibleRoot,
  CollapsibleTrigger,
} from "../aui-default/collapsible-root";
import { collapsePanel } from "../aui-default/surfaces";
import { useWorkChain, type WorkChainOptions } from "../../../trace-grouping/use-work-chain";

/** The upstream disclosure duration. */
const ANIMATION_DURATION = 200;

/**
 * The whole chain of reasoning and tool calls under one header, in the base
 * skin's look (assistant-ui's Run activity line on the theme tokens).
 *
 * When it opens and folds, and what the header says, are the digichat skin's
 * rules (`useWorkChain`): open while the agent works, folded shortly after
 * the answer starts; folded, the header is the status line ("Working —
 * web_search", "Used 3 tools"); open, it is "Working" / "Worked". Inside, the
 * reasoning box and the `N tool calls` group keep their own disclosures,
 * exactly as in the digichat skin.
 */
export function WorkChain({
  children,
  className,
  ...options
}: WorkChainOptions & { children: ReactNode; className?: string }) {
  const { open, onOpenChange, title, marker, outcome } = useWorkChain(options);
  const rootRef = useRef<HTMLDivElement | null>(null);
  // Upstream: lock the thread viewport's scroll before the panel animates.
  const lockScroll = useScrollLock(rootRef, ANIMATION_DURATION);
  const busy = marker === "loading";

  return (
    <CollapsibleRoot
      ref={rootRef}
      data-slot="aui_work-chain"
      data-outcome={outcome}
      open={open}
      onOpenChange={(next) => {
        lockScroll();
        onOpenChange(next);
      }}
      className={cn("aui-work-chain my-1 flex min-w-0 flex-col", className)}
    >
      <CollapsibleTrigger
        data-slot="aui_work-chain-trigger"
        aria-busy={busy || undefined}
        className="aui-work-chain-trigger group/trigger text-muted-foreground hover:text-foreground focus-visible:ring-ring/50 flex max-w-full items-center gap-1.5 rounded-md py-1 text-sm outline-none focus-visible:ring-[3px]"
      >
        <ChevronRightIcon
          aria-hidden="true"
          className="size-3.5 shrink-0 transition-transform duration-200 group-data-panel-open/trigger:rotate-90 group-data-open/trigger:rotate-90 motion-reduce:transition-none"
        />
        <span
          data-slot="aui_work-chain-title"
          className={cn(
            "text-start tabular-nums wrap-anywhere",
            busy && "shimmer motion-reduce:animate-none",
          )}
        >
          {title}
        </span>
        {marker === "loading" && (
          <LoaderIcon
            aria-hidden="true"
            className="size-3 shrink-0 animate-spin [animation-duration:0.6s] motion-reduce:animate-none"
          />
        )}
        {marker === "error" && (
          <CircleAlertIcon aria-hidden="true" className="text-destructive size-3.5 shrink-0" />
        )}
        {marker === "stop" && (
          <CircleStopIcon aria-hidden="true" className="size-3.5 shrink-0" />
        )}
      </CollapsibleTrigger>
      <CollapsibleContent
        // Kept mounted: the rows inside keep their own state while folded.
        keepMounted
        data-slot="aui_work-chain-content"
        className={collapsePanel}
      >
        <div className="border-border ms-1.5 flex min-w-0 flex-col gap-1 border-s ps-3.5 pt-1 text-sm wrap-anywhere">
          {children}
        </div>
      </CollapsibleContent>
    </CollapsibleRoot>
  );
}
