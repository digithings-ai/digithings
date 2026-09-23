"use client";

import { useCallback, useEffect, useRef, useState, type ReactNode } from "react";

/**
 * The horizontal card rail — a row that scrolls sideways, snaps, and fades at
 * both edges so it reads as a strip that continues past the frame.
 *
 * Promoted from the design reference's changelog rail (`apps/reference`, the
 * data page's "Content that scrolls sideways"), which the owner pointed at as
 * the treatment he wants for the strategy cards and the per-module releases:
 * "put them all in a horizontal scrollable pane like you'll find in the data
 * page ... it's the changelog rail". The mechanics (snap, hidden scrollbar,
 * edge fade, paging arrows) lived in the reference app's own CSS; they live
 * here now so both rails in digithings-web are the same component.
 *
 * The rail knows nothing about its children. Give each child a flex basis and
 * `snap-start` and it pages; the reference does it with
 * `flex-[0_0_16.5rem] snap-start`.
 *
 * Arrows are a convenience, not the only way through: the track is focusable
 * and scrolls with the keyboard, and it is the sanctioned mobile fallback for
 * any band too wide to stack.
 */
export type CardRailProps = {
  children: ReactNode;
  /** Accessible name for the scroll region, e.g. "Flagship strategies". */
  ariaLabel: string;
  className?: string;
};

export function CardRail({ children, ariaLabel, className }: CardRailProps) {
  const railRef = useRef<HTMLDivElement | null>(null);
  const [atStart, setAtStart] = useState(true);
  const [atEnd, setAtEnd] = useState(false);

  const update = useCallback(() => {
    const el = railRef.current;
    if (!el) return;
    setAtStart(el.scrollLeft <= 1);
    setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 1);
  }, []);

  useEffect(() => {
    const el = railRef.current;
    if (!el) return;
    update();
    /* A rail opens at its first card. Scroll-snap can restore a previous offset
       and a padded track can settle a pixel or two in, either of which faded the
       first card on load — the owner: "it should default to being scrolled all
       the way to the left ... it fades out the first card". Re-asserted after
       the first paint, because the snap position is applied after layout. */
    el.scrollLeft = 0;
    const raf = requestAnimationFrame(() => {
      el.scrollLeft = 0;
    });
    el.addEventListener("scroll", update, { passive: true });
    const observer = typeof ResizeObserver === "undefined" ? null : new ResizeObserver(update);
    observer?.observe(el);
    return () => {
      cancelAnimationFrame(raf);
      el.removeEventListener("scroll", update);
      observer?.disconnect();
    };
  }, [update]);

  const page = (direction: 1 | -1) => {
    const el = railRef.current;
    if (!el) return;
    el.scrollBy({
      left: direction * Math.max(el.clientWidth * 0.8, 240),
      behavior: "smooth",
    });
  };

  return (
    <div className={["cr", className].filter(Boolean).join(" ")}>
      <div className="cr-nav">
        <button
          type="button"
          className="cr-arrow"
          onClick={() => page(-1)}
          disabled={atStart}
          aria-label="Scroll left"
        >
          <span aria-hidden="true">←</span>
        </button>
        <button
          type="button"
          className="cr-arrow"
          onClick={() => page(1)}
          disabled={atEnd}
          aria-label="Scroll right"
        >
          <span aria-hidden="true">→</span>
        </button>
      </div>
      <div className="cr-mask">
        <div
          ref={railRef}
          className="cr-track"
          role="list"
          aria-label={ariaLabel}
          tabIndex={0}
        >
          {children}
        </div>
      </div>
    </div>
  );
}
