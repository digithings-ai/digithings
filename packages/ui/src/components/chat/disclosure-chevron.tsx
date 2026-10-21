"use client";

import { ScreenReaderOnly } from "./screen-reader-only";

/**
 * The one caret for every collapsible row in the trace.
 *
 * A right chevron, 0.55rem. Closed, it stays right. Open, the skin stylesheet
 * rotates this svg 90° so it points down. The rotate is on
 * `disclosure-chevron-icon` only — never this wrapper, the trigger, or the
 * label. The screen-reader name is a sibling of the svg, clipped so it does
 * not paint. The caret is a direct child of its trigger, and the rotation
 * follows that trigger: `aria-expanded` and `data-panel-open` (Base UI) or
 * `data-state="open"` (Radix). An open ancestor — the work chain's
 * `data-open` — does not rotate the closed rows inside it.
 */
export function DisclosureChevron({ label }: { label: string }) {
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
      <svg
        data-slot="disclosure-chevron-icon"
        viewBox="0 0 12 12"
        width="100%"
        height="100%"
        aria-hidden="true"
        focusable="false"
        style={{ display: "block", width: "100%", height: "100%" }}
      >
        <path
          d="M3.2 1.7 8.7 6 3.2 10.3"
          fill="none"
          stroke="currentColor"
          strokeWidth="1.9"
          strokeLinecap="round"
          strokeLinejoin="round"
        />
      </svg>
      <ScreenReaderOnly>{label}</ScreenReaderOnly>
    </span>
  );
}
