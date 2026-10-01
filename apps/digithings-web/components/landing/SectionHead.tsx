import type { ElementType, ReactNode } from "react";

/**
 * A landing band's heading: the band's h2 and an optional one-line lede. The h2
 * uses the `--type-section-stand` step every band shares.
 */
export function SectionHead({
  title,
  lede,
  as: Heading = "h2",
  className = "",
  titleClassName = "",
}: {
  title?: ReactNode;
  lede?: ReactNode;
  as?: ElementType;
  className?: string;
  titleClassName?: string;
}) {
  return (
    <header className={`flex flex-col gap-[0.7rem] ${className}`}>
      {title ? (
        <Heading className={`m-0 font-display text-[length:var(--type-section-stand)] font-medium leading-[1.2] tracking-[-0.025em] text-balance text-ink ${titleClassName}`}>
          {title}
        </Heading>
      ) : null}
      {lede ? (
        <p className="m-0 max-w-[var(--measure-prose)] text-[0.9375rem] leading-[1.65] text-ink-soft">
          {lede}
        </p>
      ) : null}
    </header>
  );
}
