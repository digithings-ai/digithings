'use client';

/**
 * A compact run-over-run delta glyph (or a "NEW" badge when there's no prior).
 *
 * F5 ruling (#1450): stays LOCAL — no @digithings/web Badge variant renders
 * this dress. The NEW chip is a filled accent chip (bg-accent/15, 4px radius,
 * 10px type); the shared reference dress is the bordered .dg-tier mono
 * micro-caps pill (no fill) and the chat dress has no accent-fill variant.
 * The delta glyph is bare money-tone typography, not a pill at all.
 */
export interface DeltaChipProps {
  delta: number | null;
  decimals?: number;
  isNew?: boolean;
  className?: string;
}

export default function DeltaChip({ delta, decimals = 2, isNew, className }: DeltaChipProps) {
  if (delta == null && !isNew) return null;

  if (isNew) {
    return (
      <span
        className={`text-[10px] rounded bg-accent/15 text-accent px-1${
          className ? ` ${className}` : ''
        }`}
      >
        NEW
      </span>
    );
  }

  const value = delta ?? 0;
  const isUp = value > 0.005;
  const isDown = value < -0.005;
  const glyph = isUp ? '▲' : isDown ? '▼' : '■';
  const tone = isUp ? 'text-accent' : isDown ? 'text-warn' : 'text-ink-mute';
  const sign = isUp ? '+' : '';
  const label = `${glyph}${sign}${value.toFixed(decimals)}`;

  return (
    <span
      className={`tabular-nums text-[10px] font-mono ${tone}${className ? ` ${className}` : ''}`}
    >
      {label}
    </span>
  );
}
