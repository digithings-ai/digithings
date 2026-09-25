import type { ReactNode } from "react";

import { cn } from "../../lib/utils";

/**
 * The framed document column (D1, #4429).
 *
 * Every marketing page is one bordered column rather than a stack of
 * full-bleed bands: a 1px hairline on each side, the page's own padding
 * inside, and the header/footer hairlines closing the frame so the page
 * reads as a single document. Below ~1040px the side borders are dropped
 * because the viewport has no room to spare.
 *
 * Utilities only — no site/app CSS class. The column width and inline
 * inset come from `--frame-w` / `--page-pad`.
 */
export interface DocumentFrameProps {
  children: ReactNode;
  className?: string;
}

export function DocumentFrame({ children, className }: DocumentFrameProps) {
  return (
    <div
      className={cn(
        "mx-auto w-full max-w-[var(--frame-w)] border-x border-hair",
        "max-[1040px]:border-x-0",
        className,
      )}
    >
      {children}
    </div>
  );
}
