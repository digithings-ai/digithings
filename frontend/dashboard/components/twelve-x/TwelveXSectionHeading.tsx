import type { ReactNode } from 'react';

export function TwelveXSectionHeading({
  children,
  className,
}: {
  children: ReactNode;
  className?: string;
}) {
  return (
    <h2
      className={`font-mono text-xs font-medium uppercase tracking-[0.08em] text-ink-soft${
        className ? ` ${className}` : ''
      }`}
    >
      {children}
    </h2>
  );
}