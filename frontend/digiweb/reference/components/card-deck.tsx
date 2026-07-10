import type { ReactNode } from "react";
import { DeckCard, DeckStack } from "@digithings/web";

/**
 * Card deck — thin consumer of the promoted <DeckStack/> / <DeckCard/>
 * (@digithings/web, #1450): the sticky stacking deck (the cavemen.dev
 * pattern) with the mono progress rail. Cards pin at a cascaded top offset
 * and the next card slides up over each — the sticky mechanics, slots
 * runway, rail state and narrow-viewport collapse live in
 * @digithings/web/styles/deck.css; the deck knows nothing about card content.
 */
export type CardDeckItem = {
  id: string;
  railLabel: string;
  content: ReactNode;
};

type CardDeckProps = {
  items: CardDeckItem[];
  ariaLabel?: string;
};

export function CardDeck({ items, ariaLabel = "Card stack" }: CardDeckProps) {
  return (
    <DeckStack
      className="mt-[1.2rem]"
      ariaLabel={ariaLabel}
      rail={items.map((item) => item.railLabel)}
    >
      {items.map((item) => (
        <DeckCard key={item.id}>{item.content}</DeckCard>
      ))}
    </DeckStack>
  );
}
