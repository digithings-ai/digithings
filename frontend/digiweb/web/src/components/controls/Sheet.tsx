"use client";
/**
 * Sheet — the shared side-panel control (#1419). Behavior (modal focus trap,
 * Escape, scrim dismiss, aria wiring) comes entirely from @base-ui/react's
 * Dialog; this file only skins it. The wrapper surface is a 1:1 prop-API
 * match for digichat's src/components/ui/sheet.tsx (side, showCloseButton,
 * Header/Footer/Title/Description parts) so a thin re-export can replace
 * that file, and the skin reproduces digichat's rendered look exactly:
 * bg scrim at 10% + blur (kept over the canon bg-black/NN dim layer — noted
 * delta), bg panel with a hair border on the attached edge, 2.5rem slide.
 * The reference controls family has no sheet counterpart, so there is no
 * skin="reference" here. The close button reproduces digichat's Button
 * variant=ghost size=icon-sm dress without depending on a Button component.
 *
 * Per-side geometry, slide transforms, scrim blur, and the close/title dress
 * live in styles/controls-overlay.css (import it once app-wide, and @source
 * this directory — see the wiring note there).
 */
import * as React from "react";
import { Dialog as SheetPrimitive } from "@base-ui/react/dialog";

import { cx, cxBase } from "./cx";

function XIcon({ className }: { className?: string }) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M18 6 6 18" />
      <path d="m6 6 12 12" />
    </svg>
  );
}

export function Sheet({ ...props }: SheetPrimitive.Root.Props) {
  return <SheetPrimitive.Root {...props} />;
}

export function SheetTrigger({ ...props }: SheetPrimitive.Trigger.Props) {
  return <SheetPrimitive.Trigger data-slot="sheet-trigger" {...props} />;
}

export function SheetClose({ ...props }: SheetPrimitive.Close.Props) {
  return <SheetPrimitive.Close data-slot="sheet-close" {...props} />;
}

export function SheetPortal({ ...props }: SheetPrimitive.Portal.Props) {
  return <SheetPrimitive.Portal {...props} />;
}

export function SheetOverlay({ className, ...props }: SheetPrimitive.Backdrop.Props) {
  return (
    <SheetPrimitive.Backdrop
      data-slot="sheet-overlay"
      className={cxBase(
        "ctl-sheet-overlay fixed inset-0 z-50 bg-bg/10 transition-opacity duration-150 data-ending-style:opacity-0 data-starting-style:opacity-0",
        className,
      )}
      {...props}
    />
  );
}

export type SheetContentProps = SheetPrimitive.Popup.Props & {
  side?: "top" | "right" | "bottom" | "left";
  showCloseButton?: boolean;
};

export function SheetContent({
  className,
  children,
  side = "right",
  showCloseButton = true,
  ...props
}: SheetContentProps) {
  return (
    <SheetPortal>
      <SheetOverlay />
      <SheetPrimitive.Popup
        data-slot="sheet-content"
        data-side={side}
        className={cxBase(
          "ctl-sheet fixed z-50 flex flex-col gap-4 bg-bg bg-clip-padding text-sm shadow-lg transition duration-200 ease-in-out data-ending-style:opacity-0 data-starting-style:opacity-0",
          className,
        )}
        {...props}
      >
        {children}
        {showCloseButton && (
          <SheetPrimitive.Close
            data-slot="sheet-close"
            className="ctl-sheet-close absolute top-3 right-3 inline-flex size-7 shrink-0 items-center justify-center border border-transparent bg-clip-padding text-sm font-medium whitespace-nowrap transition-all outline-none select-none active:translate-y-px disabled:pointer-events-none disabled:opacity-50"
          >
            <XIcon />
            <span className="sr-only">Close</span>
          </SheetPrimitive.Close>
        )}
      </SheetPrimitive.Popup>
    </SheetPortal>
  );
}

export function SheetHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-header"
      className={cx("flex flex-col gap-0.5 p-4", className)}
      {...props}
    />
  );
}

export function SheetFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="sheet-footer"
      className={cx("mt-auto flex flex-col gap-2 p-4", className)}
      {...props}
    />
  );
}

export function SheetTitle({ className, ...props }: SheetPrimitive.Title.Props) {
  return (
    <SheetPrimitive.Title
      data-slot="sheet-title"
      className={cxBase("ctl-sheet-title", className)}
      {...props}
    />
  );
}

export function SheetDescription({ className, ...props }: SheetPrimitive.Description.Props) {
  return (
    <SheetPrimitive.Description
      data-slot="sheet-description"
      className={cxBase("text-sm text-ink-soft", className)}
      {...props}
    />
  );
}
