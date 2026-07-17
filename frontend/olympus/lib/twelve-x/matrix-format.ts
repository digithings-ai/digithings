/**
 * Pure presentational helpers for the desk-view matrix and the broker drill-in.
 * Shared by MatrixTab (the grid) and BrokerProfilePanel (the single-broker
 * slide-over) so both render a desk's direction/conviction/targets identically.
 */

/** Map a currency-view direction to a .fin-* color + glyph for a matrix cell. */
export function directionStyle(direction: string): {
  text: string;
  bg: string;
  border: string;
  glyph: string;
  hoverBg: string;
  hoverBorder: string;
} {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy')
    return {
      text: 'text-up',
      bg: 'bg-up/10',
      border: 'border-up/30',
      glyph: '▲',
      hoverBg: 'hover:bg-up/[0.15]',
      hoverBorder: 'hover:border-up/50',
    };
  if (d === 'bearish' || d === 'short' || d === 'sell')
    return {
      text: 'text-down',
      bg: 'bg-down/10',
      border: 'border-down/30',
      glyph: '▼',
      hoverBg: 'hover:bg-down/[0.15]',
      hoverBorder: 'hover:border-down/50',
    };
  if (d === 'watch')
    return {
      text: 'text-warn',
      bg: 'bg-warn/10',
      border: 'border-warn/30',
      glyph: '◆',
      hoverBg: 'hover:bg-warn/[0.15]',
      hoverBorder: 'hover:border-warn/50',
    };
  return {
    text: 'text-ink-soft',
    bg: 'bg-white/[0.03]',
    border: 'border-hair',
    glyph: '•',
    hoverBg: 'hover:bg-ink/[0.06]',
    hoverBorder: 'hover:border-ink-mute/40',
  };
}

/** Coarse direction bucket for tallying a desk's net tilt. */
export function directionBucket(direction: string): 'bull' | 'bear' | 'watch' | 'neutral' {
  const d = direction.trim().toLowerCase();
  if (d === 'bullish' || d === 'long' || d === 'buy') return 'bull';
  if (d === 'bearish' || d === 'short' || d === 'sell') return 'bear';
  if (d === 'watch') return 'watch';
  return 'neutral';
}

/** Flatten a cell's broker targets (unknown[]) into a short, human-readable string. */
export function formatTargets(targets: unknown[] | undefined): string | null {
  if (!targets || targets.length === 0) return null;
  const parts = targets
    .map((t) => {
      if (typeof t === 'string' || typeof t === 'number') return String(t);
      if (t && typeof t === 'object') {
        const o = t as Record<string, unknown>;
        const label = typeof o.label === 'string' ? o.label : typeof o.type === 'string' ? o.type : null;
        const level =
          typeof o.level === 'number' || typeof o.level === 'string'
            ? String(o.level)
            : typeof o.value === 'number' || typeof o.value === 'string'
              ? String(o.value)
              : typeof o.price === 'number' || typeof o.price === 'string'
                ? String(o.price)
                : null;
        if (label && level) return `${label} ${level}`;
        return level ?? label;
      }
      return null;
    })
    .filter((p): p is string => !!p);
  return parts.length > 0 ? parts.join(', ') : null;
}

/** Conviction → opacity weight so high-conviction cells read louder. */
export function convictionOpacity(conviction: string): number {
  const c = conviction.trim().toLowerCase();
  if (c === 'high') return 1;
  if (c === 'medium' || c === 'mid') return 0.85;
  if (c === 'low') return 0.65;
  return 0.78;
}
