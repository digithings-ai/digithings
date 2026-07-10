"use client";

import {
  Children,
  cloneElement,
  isValidElement,
  memo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactElement,
  type ReactNode,
} from "react";
import { m, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "motion/react";
import type { MotionStyle, MotionValue } from "motion/react";

/**
 * DeckStack / DeckCard — the sticky stacking card deck promoted from the
 * design reference (data/card-deck; the cavemen.dev pattern, #1450). Cards
 * live in normal document flow as DIRECT children of one shared `.deck-slots`
 * grid; on wide screens each card pins at a cascaded top offset
 * (`--deck-top` + `--deck-peek` × `--stack-index`) and the next card slides
 * up over it, so every buried card keeps a visible top edge — the next
 * opaque card's coverage IS the seam (1px hairline, no drop shadow, no clip
 * box, nothing ever cut off). Content is server-rendered, fully laid out,
 * and readable top-to-bottom with no JS; the only JS enhancements are the
 * recede transform (scale + brightness while a card is covered) and the
 * optional rail's active state. Below 901px the CSS drops sticky entirely
 * and the cards simply appear in sequence. The deck knows nothing about
 * card content.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/deck.css";
 *                 @source "<path-to>/digiweb/web/src/components/deck";
 */

const WIDE_QUERY = "(min-width: 901px)";

/* useSyncExternalStore keeps the media-query state hydration-safe: the server
   snapshot is `false`, so wide-only inline transforms never appear in server
   markup and the hydrated tree matches exactly. */
function subscribeWide(callback: () => void) {
  const mq = window.matchMedia(WIDE_QUERY);
  mq.addEventListener("change", callback);
  return () => mq.removeEventListener("change", callback);
}
const getWideSnapshot = () => window.matchMedia(WIDE_QUERY).matches;
const getWideServerSnapshot = () => false;

export type DeckCardProps = {
  /** Card content — the deck stays content-agnostic. */
  children: ReactNode;
  /** Extra classes on the sticky card element — the app-dress hook. Both
   *  unlayered app CSS and call-site token utilities outrank the card's
   *  `@layer components` surface defaults in styles/deck.css. */
  className?: string;
  /** Injected by the parent DeckStack — never set manually. */
  index?: number;
  /** Injected by the parent DeckStack — never set manually. */
  total?: number;
  /** Injected by the parent DeckStack — never set manually. */
  animate?: boolean;
  /** Injected by the parent DeckStack — never set manually. */
  progress?: MotionValue<number>;
};

type AnimatedDeckCardProps = {
  children: ReactNode;
  className?: string;
  index: number;
  total: number;
  animate: boolean;
  progress: MotionValue<number>;
};

function cardClass(className?: string): string {
  return className ? `deck-card ${className}` : "deck-card";
}

/**
 * One sticky card. While the next card's slot scrolls through, this card is
 * being covered: it recedes slightly (scale + brightness) so the stack reads
 * as depth. Function transforms only — numeric range-maps get compiled to a
 * native view() timeline that cannot express this mapping (see the word
 * reveal components for the same pitfall).
 */
const AnimatedDeckCard = memo(function AnimatedDeckCard({
  children,
  className,
  index,
  total,
  animate,
  progress,
}: AnimatedDeckCardProps) {
  const cover = (p: number) => {
    if (!animate || index >= total - 1) return 0;
    const start = (index + 1) / total - 1 / total;
    return Math.min(1, Math.max(0, (p - start) * total));
  };
  const scale = useTransform(progress, (p) => 1 - cover(p) * 0.05);
  const filter = useTransform(progress, (p) => `brightness(${1 - cover(p) * 0.12})`);

  return (
    <m.article
      role="listitem"
      className={cardClass(className)}
      style={{ "--stack-index": index, scale, filter, transformOrigin: "top center" } as MotionStyle}
    >
      {children}
    </m.article>
  );
});

export function DeckCard({ children, className, index, total, animate, progress }: DeckCardProps) {
  if (progress === undefined || index === undefined || total === undefined) {
    // Rendered outside a DeckStack: a plain (still sticky-capable) card with
    // no recede transform.
    return (
      <article
        role="listitem"
        className={cardClass(className)}
        style={{ "--stack-index": index ?? 0 } as CSSProperties}
      >
        {children}
      </article>
    );
  }
  return (
    <AnimatedDeckCard
      className={className}
      index={index}
      total={total}
      animate={animate ?? false}
      progress={progress}
    >
      {children}
    </AnimatedDeckCard>
  );
}

export type DeckStackProps = {
  /** DeckCard children. They MUST render as the deck's direct children so
   *  the sticky mechanics hold — a sticky element can never leave its
   *  containing block, so a per-card wrapper would drag its card away as the
   *  wrapper scrolls past (see styles/deck.css). */
  children: ReactNode;
  /** Accessible name for the card list. */
  ariaLabel?: string;
  /** Optional progress rail: one mono label per card, pinned beside the
   *  stack on wide screens (the CSS hides it below 901px). Omit to render
   *  the slots full-width with no side column. */
  rail?: readonly string[];
  /** Accessible name for the rail list. */
  railAriaLabel?: string;
  /** Extra classes on the outer wrapper (spacing utilities etc.). */
  className?: string;
};

/**
 * The deck container: owns the shared slots grid, scroll progress, and the
 * optional side rail. Each DeckCard child is cloned with its stack index and
 * the deck's scroll progress so it can drive its own recede transform.
 */
export function DeckStack({
  children,
  ariaLabel = "Card stack",
  rail,
  railAriaLabel = "Stack progress",
  className,
}: DeckStackProps) {
  const deckRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const wide = useSyncExternalStore(subscribeWide, getWideSnapshot, getWideServerSnapshot);
  const [active, setActive] = useState(0);

  const cards = Children.toArray(children).filter(isValidElement) as ReactElement<DeckCardProps>[];
  const total = cards.length;

  const { scrollYProgress } = useScroll({
    target: deckRef,
    offset: ["start start", "end end"],
  });

  useMotionValueEvent(scrollYProgress, "change", (progress) => {
    if (total === 0) return;
    const idx = Math.min(total - 1, Math.max(0, Math.floor(progress * total)));
    setActive(idx);
  });

  const animate = wide && !reduced;

  const slots = (
    <div className="deck-slots" role="list" aria-label={ariaLabel}>
      {cards.map((card, index) =>
        cloneElement(card, { index, total, animate, progress: scrollYProgress }),
      )}
    </div>
  );

  if (!rail || rail.length === 0) {
    return (
      <div ref={deckRef} className={className}>
        {slots}
      </div>
    );
  }

  return (
    <div
      ref={deckRef}
      className={
        "grid grid-cols-[minmax(0,1fr)_220px] items-start gap-[1.2rem] max-[900px]:grid-cols-1" +
        (className ? ` ${className}` : "")
      }
    >
      {slots}
      <div className="deck-rail-pin">
        <ol className="deck-rail" aria-label={railAriaLabel}>
          {rail.map((label, idx) => (
            <li key={`${label}-${idx}`} className={idx === active ? "on" : undefined}>
              <span className="dot" />
              <span className="name">{label}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
