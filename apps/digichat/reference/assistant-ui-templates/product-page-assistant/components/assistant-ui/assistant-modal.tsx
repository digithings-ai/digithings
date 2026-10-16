"use client";

import { AssistantModalPrimitive } from "@assistant-ui/react";
import { ChevronDownIcon, LifeBuoyIcon } from "lucide-react";
import { type FC, forwardRef, type ReactNode } from "react";

import { TooltipIconButton } from "@/components/assistant-ui/tooltip-icon-button";

type AssistantModalProps = {
  triggerLabel: string;
  closeLabel: string;
  defaultOpen?: boolean;
  children: ReactNode;
};

export const AssistantModal: FC<AssistantModalProps> = ({
  triggerLabel,
  closeLabel,
  defaultOpen = false,
  children,
}) => {
  return (
    <AssistantModalPrimitive.Root defaultOpen={defaultOpen} unstable_openOnRunStart>
      <AssistantModalPrimitive.Anchor className="aui-root aui-modal-anchor fixed end-4 bottom-4 z-40 size-12">
        <AssistantModalPrimitive.Trigger asChild>
          <AssistantModalButton triggerLabel={triggerLabel} closeLabel={closeLabel} />
        </AssistantModalPrimitive.Trigger>
      </AssistantModalPrimitive.Anchor>
      <AssistantModalPrimitive.Content
        sideOffset={16}
        className="aui-root aui-modal-content data-[state=closed]:fade-out-0 data-[state=closed]:slide-out-to-bottom-1/2 data-[state=closed]:slide-out-to-right-1/2 data-[state=closed]:zoom-out data-[state=open]:fade-in-0 data-[state=open]:slide-in-from-bottom-1/2 data-[state=open]:slide-in-from-right-1/2 data-[state=open]:zoom-in bg-popover text-popover-foreground data-[state=closed]:animate-out data-[state=open]:animate-in z-50 h-[min(720px,calc(100dvh-5rem))] w-[min(440px,calc(100vw-2rem))] overflow-clip overscroll-contain rounded-lg border border-slate-200 p-0 shadow-xl outline-none [&>.aui-thread-root]:bg-inherit [&>.aui-thread-root_.aui-thread-viewport-footer]:bg-inherit"
      >
        {children}
      </AssistantModalPrimitive.Content>
    </AssistantModalPrimitive.Root>
  );
};

type AssistantModalButtonProps = {
  "data-state"?: "open" | "closed";
  triggerLabel: string;
  closeLabel: string;
};

const AssistantModalButton = forwardRef<HTMLButtonElement, AssistantModalButtonProps>(
  ({ "data-state": state, triggerLabel, closeLabel, ...rest }, ref) => {
    const tooltip = state === "open" ? closeLabel : triggerLabel;

    return (
      <TooltipIconButton
        variant="default"
        tooltip={tooltip}
        side="left"
        {...rest}
        className="aui-modal-button size-full rounded-full bg-primary text-primary-foreground shadow-lg transition-transform hover:scale-105 hover:bg-primary/90 active:scale-95"
        ref={ref}
      >
        <LifeBuoyIcon
          data-state={state}
          className="aui-modal-button-closed-icon absolute size-6 transition-all data-[state=closed]:scale-100 data-[state=closed]:rotate-0 data-[state=open]:scale-0 data-[state=open]:rotate-90"
        />

        <ChevronDownIcon
          data-state={state}
          className="aui-modal-button-open-icon absolute size-6 transition-all data-[state=closed]:scale-0 data-[state=closed]:-rotate-90 data-[state=open]:scale-100 data-[state=open]:rotate-0"
        />
        <span className="aui-sr-only sr-only">{tooltip}</span>
      </TooltipIconButton>
    );
  },
);

AssistantModalButton.displayName = "AssistantModalButton";
