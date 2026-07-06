"use client";

import {
  memo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
} from "react";
import { useMotionValueEvent, useReducedMotion, useScroll } from "motion/react";

export type CardDeckItem = {
  id: string;
  railLabel: string;
  content: ReactNode;
};

type CardDeckProps = {
  items: CardDeckItem[];
  ariaLabel?: string;
};

/* Mount gate via useSyncExternalStore: snapshot is `false` on the server and
   during hydration, `true` after mount. aria-hidden is only applied once
   mounted, so server-rendered cards stay readable without JS and the
   hydrated markup matches the server markup exactly. */
const emptySubscribe = () => () => {};
const getClientSnapshot = () => true;
const getServerSnapshot = () => false;

type DeckCardProps = {
  content: ReactNode;
  index: number;
  total: number;
  hidden: boolean;
  y: number;
};

const DeckCard = memo(function DeckCard({ content, index, total, hidden, y }: DeckCardProps) {
  return (
    <article
      role="listitem"
      className="deck-card"
      style={
        {
          top: `calc(var(--peek) * ${index})`,
          transform: `translate3d(0, ${y}px, 0)`,
          zIndex: total - index,
          "--stack-index": index,
        } as CSSProperties
      }
      aria-hidden={hidden}
    >
      {content}
    </article>
  );
});

/**
 * Generic scroll-pinned peek stack. Owns the scroll engine, pin layout,
 * stacking, and the mono progress rail — and knows nothing about card
 * content. Below 900px, CSS (.deck-* rules in data.css) degrades it to a
 * plain stacked list; reduced motion pins every card in place.
 */
export function CardDeck({ items, ariaLabel = "Card stack" }: CardDeckProps) {
  const trackRef = useRef<HTMLDivElement | null>(null);
  const reduced = useReducedMotion();
  const [active, setActive] = useState(0);
  const mounted = useSyncExternalStore(emptySubscribe, getClientSnapshot, getServerSnapshot);

  const { scrollYProgress } = useScroll({
    target: trackRef,
    offset: ["start center", "end center"],
  });

  useMotionValueEvent(scrollYProgress, "change", (progress) => {
    if (reduced) {
      setActive(items.length - 1);
      return;
    }
    const idx = Math.min(items.length - 1, Math.max(0, Math.floor(progress * items.length)));
    setActive(idx);
  });

  return (
    <div className="deck-track" ref={trackRef}>
      <div className="deck-pin">
        <div className="deck-stack" role="list" aria-label={ariaLabel}>
          {items.map((item, idx) => (
            <DeckCard
              key={item.id}
              content={item.content}
              index={idx}
              total={items.length}
              hidden={mounted && !reduced && idx > active}
              y={reduced || idx <= active ? 0 : 132}
            />
          ))}
        </div>

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
