"use client";

import { useLayoutEffect, useRef, type ReactNode } from "react";
import { Reveal } from "@digithings/ui";
import { BANDS, type BandId } from "../_bands/registry";

const pad2 = (n: number) => String(n).padStart(2, "0");

/** One band on the hairline frame. On desktop a band is one screen: at least
 *  the viewport below the nav, content centred. `fill` lets the piece grow into
 *  that screen. */
export function Band({
  id,
  title,
  takeaway,
  fill = false,
  plain = false,
  pin = false,
  children,
}: {
  id: BandId;
  title: string;
  takeaway: string;
  fill?: boolean;
  /** Skip the reveal transform. Sticky children (the workflow deck) cannot pin inside it. */
  plain?: boolean;
  /** Pin the section head (eyebrow + title + takeaway + the hairline under
   *  it) under the nav for the length of the band, so scrolling stops at
   *  that rule and the band body stacks below it as one block — the title
   *  and takeaway never separate, and nothing in the body can ride up
   *  behind either of them. The head's real rendered height (which varies
   *  with takeaway line-wrap, viewport width and font scaling — a fixed
   *  guess has undershot before and let cards stick in under the head) is
   *  measured live and written to `--band-pin-h` on the shell; the band
   *  body reads that same number as its own top offset — see the pinned
   *  band head block in app/globals.css. */
  pin?: boolean;
  children?: ReactNode;
}) {
  const shellRef = useRef<HTMLElement>(null);
  const headRef = useRef<HTMLElement>(null);

  // Keep `--band-pin-h` equal to the head's actual rendered height (not a
  // fixed guess) so the deck's sticky offset can never undershoot it —
  // undershooting is exactly what lets a card's top edge stick in behind
  // the pinned head instead of below it. Width-gated to match deck.css /
  // globals.css: below 901px neither the head nor the deck is sticky, so
  // the measurement is irrelevant there and left alone.
  useLayoutEffect(() => {
    if (!pin) return;
    const shell = shellRef.current;
    const head = headRef.current;
    if (!shell || !head) return;
    const mql = window.matchMedia("(min-width: 901px)");
    const apply = () => {
      shell.style.setProperty(
        "--band-pin-h",
        mql.matches ? `${head.getBoundingClientRect().height}px` : "0px",
      );
    };
    apply();
    const ro = new ResizeObserver(apply);
    ro.observe(head);
    mql.addEventListener("change", apply);
    return () => {
      ro.disconnect();
      mql.removeEventListener("change", apply);
    };
  }, [pin]);

  const index = BANDS.findIndex((b) => b.id === id);
  const label = BANDS[index]?.label ?? id;
  const screen = "lg:min-h-[calc(100svh-var(--nav-shell-h,62px))] lg:justify-center";
  const frameClass = `mx-auto flex w-full max-w-[var(--frame-w)] flex-col gap-[clamp(1.25rem,3vh,2.5rem)] px-[var(--page-pad)] py-[var(--page-step)] ${screen}`;
  const eyebrow = (
    <div className="flex flex-wrap items-center gap-x-4 gap-y-2">
      <p className="section-eyebrow m-0">
        <span aria-hidden="true" className="section-eyebrow__tick" />
        {pad2(index + 1)} / {label}
      </p>
    </div>
  );
  const heading = (
    <h2
      id={`${id}-h`}
      className="m-0 max-w-[28ch] font-display text-[clamp(1.5rem,3.2vw,2.25rem)] font-medium leading-[1.2] tracking-[-0.025em] text-balance text-ink"
    >
      {title}
    </h2>
  );
  const takeawayClass = "m-0 max-w-[var(--measure-prose)] text-[0.9375rem] leading-[1.65] text-ink-soft";
  const frame = (
    <>
        <header ref={pin ? headRef : undefined} className={`flex flex-col gap-[0.7rem]${pin ? " band-pin" : ""}`}>
          {eyebrow}
          {heading}
          <p className={takeawayClass}>{takeaway}</p>
        </header>
        <div id={`${id}-body`} className={fill ? "flex min-h-0 flex-1 flex-col" : "min-w-0"}>
          {children}
        </div>
    </>
  );
  return (
    <section
      ref={shellRef}
      id={id}
      aria-labelledby={`${id}-h`}
      className={`relative z-10 border-b border-hair${pin ? " band-pin-shell" : ""}`}
    >
      {plain ? <div className={frameClass}>{frame}</div> : <Reveal className={frameClass}>{frame}</Reveal>}
    </section>
  );
}
