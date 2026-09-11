"use client";

import { BotIcon, ChevronDownIcon } from "lucide-react";

import { type FC, forwardRef, type ReactNode } from "react";
import { AssistantModalPrimitive } from "@assistant-ui/react";

import { Thread } from "@/app/(baseline)/stock/thread.aui";
import { cn } from "@/lib/utils";

export const AssistantModal: FC<{
  children?: ReactNode;
  tooltipOpen?: string;
  tooltipClosed?: string;
  className?: string;
  defaultOpen?: boolean;
}> = ({
  children,
  tooltipOpen = "Close Assistant",
  tooltipClosed = "Open Assistant",
  className,
  defaultOpen = false,
}) => {
  return (
    <AssistantModalPrimitive.Root defaultOpen={defaultOpen}>
      <AssistantModalPrimitive.Anchor className="aui-root aui-modal-anchor fixed end-4 bottom-4 z-50 size-11">
        <AssistantModalPrimitive.Trigger asChild>
          <AssistantModalButton tooltipOpen={tooltipOpen} tooltipClosed={tooltipClosed} />
        </AssistantModalPrimitive.Trigger>
      </AssistantModalPrimitive.Anchor>
      <AssistantModalPrimitive.Content
        sideOffset={16}
        className={cn(
          "aui-root aui-modal-content data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-bottom-1/2 data-[state=closed]:slide-out-to-right-1/2 data-[state=closed]:zoom-out data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-bottom-1/2 data-[state=open]:slide-in-from-right-1/2 data-[state=open]:zoom-in bg-popover text-popover-foreground data-[state=closed]:animate-out data-[state=open]:animate-in z-50 h-[min(680px,calc(100dvh-6rem))] w-[min(420px,calc(100vw-2rem))] overflow-clip overscroll-contain rounded-xl border p-0 shadow-md outline-none [&>.aui-thread-root]:bg-inherit [&>.aui-thread-root_.aui-thread-viewport-footer]:bg-inherit",
          className,
        )}
      >
        {children ?? <Thread />}
      </AssistantModalPrimitive.Content>
    </AssistantModalPrimitive.Root>
  );
};

type AssistantModalButtonProps = {
  "data-state"?: "open" | "closed";
  tooltipOpen: string;
  tooltipClosed: string;
};

const AssistantModalButton = forwardRef<HTMLButtonElement, AssistantModalButtonProps>(
  ({ "data-state": state, tooltipOpen, tooltipClosed, ...rest }, ref) => {
    const tooltip = state === "open" ? tooltipOpen : tooltipClosed;

    return (
      <button
        type="button"
        aria-label={tooltip}
        title={tooltip}
        {...rest}
        className="aui-modal-button bg-primary text-primary-foreground relative flex size-full items-center justify-center rounded-full shadow transition-transform hover:scale-110 hover:bg-primary/90 active:scale-90"
        ref={ref}
      >
        <BotIcon
          data-state={state}
          className="aui-modal-button-closed-icon absolute size-6 transition-all data-[state=closed]:scale-100 data-[state=closed]:rotate-0 data-[state=open]:scale-0 data-[state=open]:rotate-90"
        />

        <ChevronDownIcon
          data-state={state}
          className="aui-modal-button-open-icon absolute size-6 transition-all data-[state=closed]:scale-0 data-[state=closed]:-rotate-90 data-[state=open]:scale-100 data-[state=open]:rotate-0"
        />
        <span className="aui-sr-only sr-only">{tooltip}</span>
      </button>
    );
  },
);

AssistantModalButton.displayName = "AssistantModalButton";
