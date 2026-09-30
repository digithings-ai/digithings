import type { ElementType, ReactNode } from "react";
import { sectionEyebrow, type LandingSectionId } from "./sections";

/**
 * A landing band's heading: a mono `NN / label` eyebrow (the same numbering as
 * the gutter rail), the band's h2, and an optional one-line lede.
 *
 * The h2 keeps the `--type-section-stand` step every band already used, so this
 * adds hierarchy above the title and rhythm below it without resizing anything.
 */
export function SectionHead({
  id,
  title,
  lede,
  as: Heading = "h2",
  className = "",
  titleClassName = "",
}: {
  id: LandingSectionId;
  title?: ReactNode;
  lede?: ReactNode;
  as?: ElementType;
  className?: string;
  titleClassName?: string;
}) {
  return (
    <header className={`flex flex-col gap-[0.7rem] ${className}`}>
      <p className="section-eyebrow m-0">
        <span aria-hidden="true" className="section-eyebrow__tick" />
        {sectionEyebrow(id)}
      </p>
      {title ? (
        <Heading className={`m-0 font-mono text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-balance text-ink ${titleClassName}`}>
          {title}
        </Heading>
      ) : null}
      {lede ? (
        <p className="m-0 max-w-[var(--measure-prose)] font-mono text-[0.875rem] leading-[1.65] text-ink-soft">
          {lede}
        </p>
      ) : null}
    </header>
  );
}
