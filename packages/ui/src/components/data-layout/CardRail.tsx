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
 * STEPPING, ONE CARD AT A TIME. The arrows move exactly one card, not a
 * viewport: the owner, "the arrows for the different tier sheet cards in the
 * horizontal scroll should cycle between one at a time. Right now it just goes
 * to the end of the horizontal scroll. Initially we should have the first
 * strategy selected and then with the arrow you scroll to the right or to the
 * left." So the rail tracks which card sits at the leading edge (the first one
 * at rest), an arrow steps to the next or previous card and scrolls it flush to
 * that edge, and the left arrow is disabled while the first card is selected.
 * The active card is marked `data-active` so a consumer can style the selection
 * (the strategy rail does, in `card-rail.css`); dragging the track re-syncs the
 * selection to whichever card it snaps to, so the mark never lies.
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
  const [activeIndex, setActiveIndex] = useState(0);
  const [count, setCount] = useState(0);

  /** The rail's cards, in order. Anything non-element is ignored. */
  const cards = useCallback((): HTMLElement[] => {
    const el = railRef.current;
    if (!el) return [];
    return Array.from(el.children).filter((child): child is HTMLElement => child instanceof HTMLElement);
  }, []);

  /** One card's width plus the gap after it — the distance an arrow travels. */
  const cardStep = useCallback((): number => {
    const [first, second] = cards();
    if (!first) return railRef.current?.clientWidth ?? 0;
    const width = first.getBoundingClientRect().width;
    const gap = second
      ? second.getBoundingClientRect().left - first.getBoundingClientRect().right
      : 0;
    return width + Math.max(gap, 0);
  }, [cards]);

  const update = useCallback(() => {
    const el = railRef.current;
    if (!el) return;
    setAtStart(el.scrollLeft <= 1);
    setAtEnd(el.scrollLeft + el.clientWidth >= el.scrollWidth - 1);
    /* The selected card is the one whose leading edge sits nearest the track's
       own leading edge — after a snap that is unambiguous, and it keeps the mark
       honest when the track is dragged rather than stepped. */
    const list = cards();
    setCount(list.length);
    if (list.length === 0) return;
    const base = el.getBoundingClientRect().left;
    let best = 0;
    let bestDistance = Number.POSITIVE_INFINITY;
    list.forEach((card, index) => {
      const distance = Math.abs(card.getBoundingClientRect().left - base);
      if (distance < bestDistance) {
        bestDistance = distance;
        best = index;
      }
    });
    setActiveIndex(best);
  }, [cards]);

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
      update();
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

  /* Mark the selected card. Deps include `children` so the mark is re-applied
     when the list itself is replaced (e.g. the live strategy read landing). */
  useEffect(() => {
    cards().forEach((card, index) => {
      if (index === activeIndex) card.setAttribute("data-active", "true");
      else card.removeAttribute("data-active");
    });
  }, [activeIndex, cards, children]);

  /** Step one card. Clamped at both ends, so the arrows never overrun. */
  const step = (direction: 1 | -1) => {
    const el = railRef.current;
    const list = cards();
    if (!el || list.length === 0) return;
    const next = Math.max(0, Math.min(list.length - 1, activeIndex + direction));
    if (next === activeIndex) return;
    setActiveIndex(next);
    /* Straight to the target card rather than to the last one: when the live
       read swaps the list, `activeIndex` and the DOM can disagree for a frame,
       and measuring sideways is what makes the arrow land where it says. */
    el.scrollBy({
      left: direction * Math.abs(cardStep()) * Math.abs(next - activeIndex),
      behavior: "smooth",
    });
  };

  const lastIndex = Math.max(0, count - 1);

  return (
    <div className={["cr", className].filter(Boolean).join(" ")} data-active-index={activeIndex}>
      <div className="cr-nav">
        <button
          type="button"
          className="cr-arrow"
          onClick={() => step(-1)}
          disabled={atStart || activeIndex <= 0}
          aria-label="Scroll left"
        >
          <span aria-hidden="true">←</span>
        </button>
        <button
          type="button"
          className="cr-arrow"
          onClick={() => step(1)}
          disabled={atEnd || activeIndex >= lastIndex}
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
