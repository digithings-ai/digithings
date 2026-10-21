"use client";

import { DotMatrix } from "./DotMatrix";

/**
 * The one caret for every collapsible row in the trace.
 *
 * The glyph points right. Closed, it stays right. Open, the skin stylesheet
 * rotates the icon svg 90° so it points down. The rotate is on
 * `dot-matrix-grid` only — never this wrapper, the trigger, or the label.
 * The wrapper also carries the screen-reader name, and turning the wrapper
 * turns those words. The caret is a direct child of its trigger, and the
 * rotation follows that trigger: `aria-expanded` and `data-panel-open`
 * (Base UI) or `data-state="open"` (Radix). An open ancestor — the work
 * chain's `data-open` — does not rotate the closed rows inside it.
 */
export function DisclosureChevron({ label }: { label: string }) {
  return (
    <span data-slot="disclosure-chevron" className="aui-disclosure-chevron">
      <DotMatrix state="expand" label={label} className="!size-[0.55rem]" />
    </span>
  );
}
