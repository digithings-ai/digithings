"use client";

/**
 * Product tooltip for the gallery Thread: the canonical kit Tooltip
 * (`@digithings/web/ui/tooltip`, Base UI) with the chat's long-standing
 * no-arrow ruling (#3818). The kit `TooltipContent` always renders its
 * rotated-square `Arrow`; the chat renders none, so the popup is tagged
 * `data-tooltip-arrow="none"` and that direct Arrow child is hidden here.
 * Behaviour (hover + focus open, Escape dismiss, aria wiring) is the kit's;
 * only the arrow is suppressed, which keeps the product's rendered look and
 * `gallery-thread.source.test.ts` intact. If the kit later grows a
 * `hideArrow` prop this adapter can collapse to a bare re-export.
 */
import type { ComponentProps } from "react";

import { TooltipContent as KitTooltipContent } from "../../../../ui/tooltip";
import { cn } from "../cn";

export { Tooltip, TooltipTrigger, TooltipProvider } from "../../../../ui/tooltip";

export function TooltipContent({
  className,
  sideOffset = 0,
  ...props
}: ComponentProps<typeof KitTooltipContent>) {
  return (
    <KitTooltipContent
      data-tooltip-arrow="none"
      sideOffset={sideOffset}
      className={cn("[&>[aria-hidden]]:hidden", className)}
      {...props}
    />
  );
}
