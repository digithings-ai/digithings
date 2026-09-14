"use client";

import { useId, useState, type ReactNode } from "react";

/**
 * Tooltip — a label that surfaces on hover and keyboard focus, fades in with a
 * small rise, and points back at its trigger with a rotated-square arrow. Escape
 * dismisses it; aria-describedby ties it to the control so it's announced. Four
 * placements, plus a richer one on an info glyph. Static interactive display
 * template.
 */
type Placement = "top" | "right" | "bottom" | "left";

function Tooltip({
  label,
  placement = "top",
  children,
}: {
  label: string;
  placement?: Placement;
  children: ReactNode;
}) {
  const [open, setOpen] = useState(false);
  const id = useId();
  return (
    <span
      className="relative inline-flex"
      onPointerEnter={() => setOpen(true)}
      onPointerLeave={() => setOpen(false)}
    >
      <button
        type="button"
        className="tt-trigger"
        aria-describedby={id}
        onFocus={() => setOpen(true)}
        onBlur={() => setOpen(false)}
        onKeyDown={(e) => {
          if (e.key === "Escape") {
            setOpen(false);
            e.currentTarget.blur();
          }
        }}
      >
        {children}
      </button>
      <span role="tooltip" id={id} className={`tt-bubble tt--${placement}${open ? " open" : ""}`}>
        {label}
      </span>
    </span>
  );
}

export function TooltipReference() {
  return (
    <section className="section-block">
      <p className="kicker">{"// tooltip"}</p>
      <h2 className="title">A hint, on demand.</h2>
      <p className="section-copy">
        A label that surfaces on hover <em>and</em> keyboard focus, fades in with a small rise, and
        points back at its trigger. Escape dismisses it; <code>aria-describedby</code> ties it to
        the control so it&apos;s announced. Four placements, and a richer one on an info glyph.
      </p>

      <div className="mt-[1.2rem] flex flex-wrap items-center gap-[1.7rem]">
        <Tooltip label="Ships to paper first" placement="top">
          top
        </Tooltip>
        <Tooltip label="Routes through the sizer" placement="right">
          right
        </Tooltip>
        <Tooltip label="Gated behind a human" placement="bottom">
          bottom
        </Tooltip>
        <Tooltip label="Replays the ledger" placement="left">
          left
        </Tooltip>

        <Tooltip label="Profit factor — gross profit ÷ gross loss. Above 1 is net positive." placement="top">
          <span className="tt-glyph" aria-hidden="true">
            <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" strokeWidth="1.7" strokeLinecap="round" strokeLinejoin="round">
              <circle cx="12" cy="12" r="9" />
              <path d="M12 11v5M12 8v.5" />
            </svg>
          </span>
          <span className="sr-only">What is profit factor?</span>
        </Tooltip>
      </div>
    </section>
  );
}
