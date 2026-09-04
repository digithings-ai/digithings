/**
 * Dialog — the shared centered modal. Behavior (modal focus trap,
 * Escape, scrim dismiss, aria wiring) comes entirely from @base-ui/react's
 * Dialog; this file only skins it. Sibling of Sheet (which wraps the same
 * primitive as a side panel): same part vocabulary (Trigger/Close/Portal/
 * Overlay/Content/Header/Footer/Title/Description), one new prop —
 * `tone="danger"` tints the title for confirm/delete flows.
 *
 * Unlike the compat-skinned controls, Dialog wears the canon dress directly
 * (there is no digichat dialog look to reproduce): radius 0, hairline,
 * `--surface` panel, canon black dim scrim. All dress lives in
 * styles/controls-overlay.css (`.ctl-dialog-*`, import once app-wide, next
 * to the Sheet dress); this file carries no Tailwind utilities, so no
 * `@source` line is needed for it. The enter/exit reuses the shared
 * `.ctl-pop` keyframes.
 */
import * as React from "react";
import { Dialog as DialogPrimitive } from "@base-ui/react/dialog";

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

export function Dialog({ ...props }: DialogPrimitive.Root.Props) {
  return <DialogPrimitive.Root {...props} />;
}

export function DialogTrigger({ ...props }: DialogPrimitive.Trigger.Props) {
  return <DialogPrimitive.Trigger data-slot="dialog-trigger" {...props} />;
}

export function DialogClose({ ...props }: DialogPrimitive.Close.Props) {
  return <DialogPrimitive.Close data-slot="dialog-close" {...props} />;
}

export function DialogPortal({ ...props }: DialogPrimitive.Portal.Props) {
  return <DialogPrimitive.Portal {...props} />;
}

export function DialogOverlay({ className, ...props }: DialogPrimitive.Backdrop.Props) {
  return (
    <DialogPrimitive.Backdrop
      data-slot="dialog-overlay"
      className={className ? `ctl-dialog-overlay ${className}` : "ctl-dialog-overlay"}
      {...props}
    />
  );
}

export type DialogContentProps = DialogPrimitive.Popup.Props & {
  /** `danger` tints the title `--danger` for confirm/delete flows. */
  tone?: "default" | "danger";
  showCloseButton?: boolean;
};

export function DialogContent({
  className,
  children,
  tone = "default",
  showCloseButton = true,
  ...props
}: DialogContentProps) {
  return (
    <DialogPortal>
      <DialogOverlay />
      <DialogPrimitive.Popup
        data-slot="dialog-content"
        data-tone={tone}
        className={className ? `ctl-dialog-popup ctl-pop ${className}` : "ctl-dialog-popup ctl-pop"}
        {...props}
      >
        <div className="ctl-dialog-card" data-tone={tone} role="presentation">
          {children}
          {showCloseButton && (
            <DialogPrimitive.Close
              data-slot="dialog-close"
              className="ctl-dialog-x"
              aria-label="Close dialog"
            >
              <XIcon />
            </DialogPrimitive.Close>
          )}
        </div>
      </DialogPrimitive.Popup>
    </DialogPortal>
  );
}

export function DialogHeader({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-header"
      className={className ? `ctl-dialog-header ${className}` : "ctl-dialog-header"}
      {...props}
    />
  );
}

export function DialogFooter({ className, ...props }: React.ComponentProps<"div">) {
  return (
    <div
      data-slot="dialog-footer"
      className={className ? `ctl-dialog-footer ${className}` : "ctl-dialog-footer"}
      {...props}
    />
  );
}

export function DialogTitle({ className, ...props }: DialogPrimitive.Title.Props) {
  return (
    <DialogPrimitive.Title
      data-slot="dialog-title"
      className={className ? `ctl-dialog-title ${className}` : "ctl-dialog-title"}
      {...props}
    />
  );
}

export function DialogDescription({ className, ...props }: DialogPrimitive.Description.Props) {
  return (
    <DialogPrimitive.Description
      data-slot="dialog-description"
      className={className ? `ctl-dialog-description ${className}` : "ctl-dialog-description"}
      {...props}
    />
  );
}
