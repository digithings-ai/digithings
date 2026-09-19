"use client";

import { cn } from "@/lib/utils";
import { forwardRef, type ButtonHTMLAttributes, type ReactNode } from "react";

type TooltipIconButtonProps = ButtonHTMLAttributes<HTMLButtonElement> & {
  tooltip?: string;
  side?: "top" | "right" | "bottom" | "left";
  variant?: string;
  size?: string;
  children?: ReactNode;
};

export const TooltipIconButton = forwardRef<HTMLButtonElement, TooltipIconButtonProps>(
  function TooltipIconButton(
    { tooltip, className, children, variant: _variant, size: _size, side: _side, ...props },
    ref,
  ) {
    return (
      <button
        type="button"
        ref={ref}
        aria-label={tooltip}
        title={tooltip}
        className={cn(
          "inline-flex size-8 items-center justify-center rounded-md transition-colors hover:bg-muted disabled:opacity-50",
          className,
        )}
        {...props}
      >
        {children}
      </button>
    );
  },
);
