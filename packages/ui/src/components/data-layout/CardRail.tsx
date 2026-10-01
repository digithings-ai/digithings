"use client";

import { Children, useCallback, useEffect, useRef, useState, type ReactNode } from "react";
import { IconButton } from "../../ui";
import { cn } from "../../lib/utils";
import { clamp, nearestIndex } from "../effects-chrome/horizontal-track-core";

/**
 * CardRail — a horizontal rail of cards on NATIVE scroll-snap: swipe, wheel,
 * arrow keys, or the prev / next buttons (one card per press). Edge fades read
 * the strip as continuing past the frame. No pin, no transform, no JS needed to
 * scroll — the buttons are an enhancement over a fully working native rail.
 *
 * Re-authored from the design reference's changelog rail (and the refactor
 * branch's rail) as a utilities-only part: no CSS sheet, no `.cr-*` classes.
 * The edge fade is a mask over token stops (alpha only, no raw colour).
 *
 * Each child is wrapped in a `role="listitem"` snap target. The wrapper carries
 * `data-active="true"` on the card at the leading edge (a `group/card`, so a
 * child can style `group-data-[active=true]/card:border-accent` without the rail
 * knowing anything about it). The wrapper is not a tab stop — put links and
 * buttons inside the cards; focusing one scrolls the rail natively. The track
 * itself is focusable so a keyboard user can scroll it with the arrow keys.
 *
 * Reveal-safe: the track carries vertical padding so a `Reveal` child's rise
 * (translateY) is not clipped by the rail's overflow, and wrappers never
 * transform. With no JS and under reduced motion every card is reachable.
 *
 * Stepping is instant under `prefers-reduced-motion` (CSS `scroll-behavior`
 * smooth is applied only when motion is allowed).
 *
 * Wiring (in the consuming app):
 *   globals.css   @source "<path-to>/packages/ui/src/components/data-layout";
 */
export type CardRailProps = {
  /** The cards. Each direct child becomes one snap item. */
  children: ReactNode;
  /** Accessible name for the scroll region, e.g. "Strategy tearsheets". */
  ariaLabel: string;
  /** Left of the prev / next buttons (a title, a count). */
  header?: ReactNode;
  /** Classes on each snap-item wrapper (sets the card width). */
  itemClassName?: string;
  /** Classes on the outermost element. */
  className?: string;
  /** Accessible names for the two buttons. */
  prevLabel?: string;
  nextLabel?: string;
};

// Alpha stops through a token — a mask reads alpha only, so no raw colour.
const FADE =
  "[mask-image:linear-gradient(90deg,transparent,var(--ink)_1.5rem,var(--ink)_calc(100%_-_1.5rem),transparent)]";

function offsetsOf(track: HTMLElement): number[] {
  const kids = Array.from(track.children).filter((c): c is HTMLElement => c instanceof HTMLElement);
  const base = kids[0]?.offsetLeft ?? 0;
  return kids.map((k) => k.offsetLeft - base);
}

export function CardRail({
  children,
  ariaLabel,
  header,
  itemClassName,
  className,
  prevLabel = "Previous card",
  nextLabel = "Next card",
}: CardRailProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const items = Children.toArray(children);
  const [active, setActive] = useState(0);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  const sync = useCallback(() => {
    const el = trackRef.current;
    if (!el) return;
    setAtStart(el.scrollLeft <= 1);
    setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 1);
    setActive(nearestIndex(offsetsOf(el), el.scrollLeft));
  }, []);

  useEffect(() => {
    const el = trackRef.current;
    if (!el) return;
    sync();
    el.addEventListener("scroll", sync, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(sync);
    observer?.observe(el);
    return () => {
      el.removeEventListener("scroll", sync);
      observer?.disconnect();
    };
  }, [sync, items.length]);

  const step = (direction: 1 | -1) => {
    const el = trackRef.current;
    if (!el) return;
    const offsets = offsetsOf(el);
    const next = clamp(active + direction, 0, offsets.length - 1);
    el.scrollTo({ left: offsets[next] ?? 0 });
  };

  return (
    <div className={cn("grid gap-3", className)} data-card-rail="">
      <div className="flex items-end justify-between gap-4">
        <div className="min-w-0">{header}</div>
        <div className="flex shrink-0 gap-[0.4rem]">
          <IconButton
            aria-label={prevLabel}
            onClick={() => step(-1)}
            disabled={atStart}
            className="border border-hair"
          >
            <span aria-hidden="true">{"←"}</span>
          </IconButton>
          <IconButton
            aria-label={nextLabel}
            onClick={() => step(1)}
            disabled={atEnd}
            className="border border-hair"
          >
            <span aria-hidden="true">{"→"}</span>
          </IconButton>
        </div>
      </div>
      <div className={FADE}>
        <div
          ref={trackRef}
          role="list"
          aria-label={ariaLabel}
          tabIndex={0}
          className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-ps-6 px-6 py-4 outline-none [scrollbar-width:none] motion-safe:scroll-smooth focus-visible:outline focus-visible:outline-1 focus-visible:-outline-offset-1 focus-visible:outline-accent [&::-webkit-scrollbar]:hidden"
        >
          {items.map((child, i) => (
            <div
              key={i}
              role="listitem"
              data-active={i === active ? "true" : undefined}
              className={cn("group/card relative flex-none snap-start w-[min(82vw,17rem)]", itemClassName)}
            >
              {child}
            </div>
          ))}
        </div>
      </div>
    </div>
  );
}
