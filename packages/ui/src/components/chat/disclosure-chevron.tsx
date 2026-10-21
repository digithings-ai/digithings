"use client";

import { DotMatrix } from "./DotMatrix";

/**
 * The one caret for every collapsible row in the trace.
 *
 * The same square pixel chevron as the mark beside a user message
 * (`DotMatrix` state `user`), in the 0.55rem box the trace caret had before.
 * Closed, it points right. Open, the skin stylesheet rotates the cube svg
 * 90° so it points down. The rotate is on `dot-matrix-grid` only — never
 * this wrapper, the trigger, or the label. The glyph is decorative: every
 * trigger it sits in is named by its visible text (DIG-4669), and the open
 * state is the trigger's `aria-expanded`. The caret is a direct child of its
 * trigger, and the rotation follows that trigger:
 * `aria-expanded` and `data-panel-open` (Base UI) or `data-state="open"`
 * (Radix). An open ancestor — the work chain's `data-open` — does not
 * rotate the closed rows inside it.
 */
export function DisclosureChevron() {
  return (
    <span
      data-slot="disclosure-chevron"
      className="aui-disclosure-chevron"
      style={{
        position: "relative",
        display: "inline-flex",
        width: "0.55rem",
        height: "0.55rem",
        flex: "0 0 0.55rem",
      }}
    >
      <DotMatrix state="user" decorative className="!size-[0.55rem]" />
    </span>
  );
}
