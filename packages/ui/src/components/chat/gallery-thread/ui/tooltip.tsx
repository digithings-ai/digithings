"use client";

/**
 * Product tooltip for the gallery Thread: the canonical kit Tooltip
 * (`@digithings/ui/ui/tooltip`, Base UI) with the chat's long-standing
 * no-arrow ruling (#3818) via the kit's `hideArrow` prop, and a zero
 * `sideOffset` default. Behaviour (hover + focus open, Escape dismiss, aria
 * wiring) is the kit's; only the arrow is suppressed, which keeps the
 * product's rendered look and `gallery-thread.source.test.ts` intact.
 */
import type { ComponentProps } from "react";

import { TooltipContent as KitTooltipContent } from "../../../../ui/tooltip";

export { Tooltip, TooltipTrigger, TooltipProvider } from "../../../../ui/tooltip";

export function TooltipContent({
  sideOffset = 0,
  ...props
}: ComponentProps<typeof KitTooltipContent>) {
  return <KitTooltipContent hideArrow sideOffset={sideOffset} {...props} />;
}
