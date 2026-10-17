import type { ReactNode } from "react";

import { cn } from "../../lib/utils";
import { LayoutLines } from "../page-geometry";

/**
 * The framed document column (D1, #4429).
 *
 * Every marketing page sits between the same fixed dashed rails as the
 * landing page (`LayoutLines`), one `--page-pad` outside the content column,
 * so a subpage and the home page read as the same built object. Section
 * hairlines are full-bleed and cross the rails, as the landing bands do; the
 * outer wrapper clips them to the viewport so they never add a horizontal
 * scroll.
 *
 * The frame also resets the counter the section headings number themselves
 * from (`// 01`, `// 02`, …).
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
    <>
      <LayoutLines />
      <div className="relative z-10 overflow-x-clip [counter-reset:doc-section]">
        <div
          className={cn(
            "mx-auto w-full max-w-[calc(var(--frame-w)+2*var(--page-pad))]",
            className,
          )}
        >
          {children}
        </div>
      </div>
    </>
  );
}
