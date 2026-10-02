"use client";

import { useState, type ReactNode } from "react";
import { Reveal } from "@digithings/ui";
import { Badge, Button } from "@digithings/ui/ui";
import { BANDS, type BandId } from "../_bands/registry";

const pad2 = (n: number) => String(n).padStart(2, "0");

/** One band on the hairline frame. On desktop an open band is one screen: at least
 *  the viewport below the nav, content centred. `fill` lets the piece grow into
 *  that screen. The header can collapse the band so a long page still fits. */
export function Band({
  id,
  title,
  takeaway,
  status = "placeholder",
  fill = false,
  plain = false,
  children,
}: {
  id: BandId;
  title: string;
  takeaway: string;
  status?: string;
  fill?: boolean;
  /** Skip the reveal transform. Sticky children (the workflow deck) cannot pin inside it. */
  plain?: boolean;
  children?: ReactNode;
}) {
  const [open, setOpen] = useState(true);
  const index = BANDS.findIndex((b) => b.id === id);
  const label = BANDS[index]?.label ?? id;
  const screen = open ? "lg:min-h-[calc(100svh-var(--nav-shell-h,62px))] lg:justify-center" : "";
  const frameClass = `mx-auto flex w-full max-w-[var(--frame-w)] flex-col gap-[clamp(1.25rem,3vh,2.5rem)] px-[var(--page-pad)] py-[var(--page-step)] ${screen}`;
  const frame = (
    <>
        <header className="flex flex-col gap-[0.7rem]">
          <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
            <p className="section-eyebrow m-0">
              <span aria-hidden="true" className="section-eyebrow__tick" />
              {pad2(index + 1)} / {label}
            </p>
            <Badge variant="neutral">{status}</Badge>
            <Button
              type="button"
              variant="ghost"
              size="xs"
              aria-expanded={open}
              aria-controls={`${id}-body`}
              onClick={() => setOpen((v) => !v)}
            >
              {open ? "Collapse" : "Expand"}
            </Button>
          </div>
          <h2
            id={`${id}-h`}
            className="m-0 max-w-[28ch] font-display text-[clamp(1.5rem,3.2vw,2.25rem)] font-medium leading-[1.2] tracking-[-0.025em] text-balance text-ink"
          >
            {title}
          </h2>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9375rem] leading-[1.65] text-ink-soft">{takeaway}</p>
        </header>
        {open ? (
          <div id={`${id}-body`} className={fill ? "flex min-h-0 flex-1 flex-col" : "min-w-0"}>
            {children}
          </div>
        ) : null}
    </>
  );
  return (
    <section id={id} aria-labelledby={`${id}-h`} className="relative z-10 border-b border-hair">
      {plain ? <div className={frameClass}>{frame}</div> : <Reveal className={frameClass}>{frame}</Reveal>}
    </section>
  );
}
