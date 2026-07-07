"use client";

import { memo, useRef, useState, useSyncExternalStore, type ReactNode } from "react";
import { m, useMotionValueEvent, useReducedMotion, useScroll, useTransform } from "motion/react";
import type { MotionStyle, MotionValue } from "motion/react";

export type CardDeckItem = {
  id: string;
  railLabel: string;
  content: ReactNode;
};

type CardDeckProps = {
  items: CardDeckItem[];
  ariaLabel?: string;
};

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

type DeckCardProps = {
  content: ReactNode;
  index: number;
  total: number;
  animate: boolean;
  progress: MotionValue<number>;
};

/**
 * One sticky card. While the next card's slot scrolls through, this card is
 * being covered: it recedes slightly (scale + brightness) so the stack reads
 * as depth. Function transforms only — numeric range-maps get compiled to a
 * native view() timeline that cannot express this mapping (see the word
 * reveal components for the same pitfall).
 */
const DeckCard = memo(function DeckCard({ content, index, total, animate, progress }: DeckCardProps) {
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
      className="deck-card"
      style={{ "--stack-index": index, scale, filter, transformOrigin: "top center" } as MotionStyle}
    >
      {content}
    </m.article>
  );
});

/**
 * Sticky stacking deck (the cavemen.dev pattern): cards live in normal
 * document flow; each pins at a cascaded top offset and the next card slides
 * up over it, accumulating a stack whose edges stay visible. Below 901px the
 * CSS (.deck-* rules in data.css) drops sticky entirely and the cards simply
 * appear in sequence. The deck knows nothing about card content.
 */
export function CardDeck({ items, ariaLabel = "Card stack" }: CardDeckProps) {
  const deckRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const wide = useSyncExternalStore(subscribeWide, getWideSnapshot, getWideServerSnapshot);
  const [active, setActive] = useState(0);

  const { scrollYProgress } = useScroll({
    target: deckRef,
    offset: ["start start", "end end"],
  });

  useMotionValueEvent(scrollYProgress, "change", (progress) => {
    const idx = Math.min(items.length - 1, Math.max(0, Math.floor(progress * items.length)));
    setActive(idx);
  });

  const animate = wide && !reduced;

  return (
    <div
      className="mt-[1.2rem] grid grid-cols-[minmax(0,1fr)_220px] items-start gap-[1.2rem] max-[900px]:grid-cols-1"
      ref={deckRef}
    >
      <div className="deck-slots" role="list" aria-label={ariaLabel}>
        {items.map((item, idx) => (
          <DeckCard
            key={item.id}
            content={item.content}
            index={idx}
            total={items.length}
            animate={animate}
            progress={scrollYProgress}
          />
        ))}
      </div>

      <div className="deck-rail-pin">
        <ol className="deck-rail" aria-label="Stack progress">
          {items.map((item, idx) => (
            <li key={item.id} className={idx === active ? "on" : undefined}>
              <span className="dot" />
              <span className="name">{item.railLabel}</span>
            </li>
          ))}
        </ol>
      </div>
    </div>
  );
}
