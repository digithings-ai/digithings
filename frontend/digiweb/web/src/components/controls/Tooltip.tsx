"use client";
/**
 * Tooltip — the shared hover/focus hint (#1419). Behavior (hover + focus
 * open, Escape dismiss, delay grouping via Provider, aria wiring) comes
 * entirely from @base-ui/react's Tooltip; this file only skins it. The
 * wrapper surface is a 1:1 prop-API match for digichat's
 * src/components/ui/tooltip.tsx (Provider delay default 0, Content
 * side/sideOffset/align/alignOffset with an arrow) so a thin re-export can
 * replace that file. The DEFAULT skin reproduces digichat's rendered look
 * exactly: the inverted bubble (ink surface, bg-colored text, rotated-square
 * ink arrow). `skin="reference"` opts into the reference controls-family
 * tt-bubble grammar instead (surface pane, hair border, mono type, bordered
 * arrow) — the reference-vs-digichat delta is a pending product ruling.
 *
 * Bubble/arrow colors, per-side arrow placement, and the enter/exit
 * animation live in styles/controls-overlay.css (import it once app-wide,
 * and @source this directory — see the wiring note there).
 */
import { Tooltip as TooltipPrimitive } from "@base-ui/react/tooltip";

import { cx, cxBase } from "./cx";
import type { ControlSkin } from "./DropdownMenu";

export function TooltipProvider({ delay = 0, ...props }: TooltipPrimitive.Provider.Props) {
  return <TooltipPrimitive.Provider delay={delay} {...props} />;
}

export function Tooltip({ ...props }: TooltipPrimitive.Root.Props) {
  return <TooltipPrimitive.Root {...props} />;
}

export function TooltipTrigger({ ...props }: TooltipPrimitive.Trigger.Props) {
  return <TooltipPrimitive.Trigger data-slot="tooltip-trigger" {...props} />;
}

export type TooltipContentProps = TooltipPrimitive.Popup.Props &
  Pick<TooltipPrimitive.Positioner.Props, "align" | "alignOffset" | "side" | "sideOffset"> & {
    /** "chat" (default) = digichat's inverted bubble; "reference" = tt-bubble grammar. */
    skin?: ControlSkin;
  };

export function TooltipContent({
  className,
  side = "top",
  sideOffset = 4,
  align = "center",
  alignOffset = 0,
  skin = "chat",
  children,
  ...props
}: TooltipContentProps) {
  return (
    <TooltipPrimitive.Portal>
      <TooltipPrimitive.Positioner
        align={align}
        alignOffset={alignOffset}
        side={side}
        sideOffset={sideOffset}
        className="isolate z-50"
      >
        <TooltipPrimitive.Popup
          data-slot="tooltip-content"
          className={cxBase(
            cx(
              "ctl-tip ctl-pop z-50 inline-flex w-fit max-w-xs origin-(--transform-origin) items-center gap-1.5 rounded-md px-3 py-1.5 text-xs",
              skin === "reference" && "ctl-tip--ref",
            ),
            className,
          )}
          {...props}
        >
          {children}
          <TooltipPrimitive.Arrow className="ctl-tip-arrow z-50" />
        </TooltipPrimitive.Popup>
      </TooltipPrimitive.Positioner>
    </TooltipPrimitive.Portal>
  );
}
