import type { ReactNode } from "react";

/**
 * BentoGrid + BentoCell — the asymmetric bento layout promoted from the design
 * reference (layout-patterns/bento-grid): a 4-column grid where cell weight
 * signals hierarchy — `hero` anchors 2×2, `wide` runs two columns, `tall` two
 * rows, `unit` takes one. Each cell may scope a module livery (`accent-<id>`,
 * declared in @digithings/design/tokens.css) that tints the ::before hover
 * hairline and the hero wash (styles/data-layout.css). Content is entirely
 * children-driven — the cell only owns the frame; a heading inside a hero cell
 * should carry the `bento-name` class to pick up the hero's larger type.
 * Collapses to one column below 760px. Server components — no state.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/data-layout.css";
 *                 @source "<path-to>/digiweb/web/src/components/data-layout";
 */
export type BentoSpan = "hero" | "wide" | "tall" | "unit";

export function BentoGrid({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return <div className={`bento-grid${className ? ` ${className}` : ""}`}>{children}</div>;
}

export function BentoCell({
  span = "unit",
  livery,
  className,
  children,
}: {
  /** Cell weight — hero 2×2, wide 2×1, tall 1×2, unit 1×1. */
  span?: BentoSpan;
  /** Optional module livery scope — suffix of an `accent-<module>` class. */
  livery?: string;
  className?: string;
  children: ReactNode;
}) {
  return (
    <article
      className={`bento-cell flex flex-col justify-between rounded-[12px] border border-hair p-[1.1rem] bento-${span}${
        livery ? ` accent-${livery}` : ""
      }${className ? ` ${className}` : ""}`}
    >
      {children}
    </article>
  );
}
