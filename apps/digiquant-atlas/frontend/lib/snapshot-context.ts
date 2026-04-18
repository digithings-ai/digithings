/**
 * Defensive extraction of human-readable bullets from snapshot JSON
 * (segment_biases, market_data) for Overview / Strategy footnotes.
 */

function pushUnique(out: string[], line: string, max: number) {
  const t = line.trim();
  if (!t || out.length >= max) return;
  if (out.includes(t)) return;
  out.push(t.length > 160 ? `${t.slice(0, 157)}…` : t);
}

export function extractSnapshotContextBullets(
  segment_biases: unknown,
  market_data: unknown,
  max = 5
): string[] {
  const out: string[] = [];

  if (Array.isArray(segment_biases)) {
    for (const item of segment_biases) {
      if (out.length >= max) break;
      if (typeof item === 'string') {
        pushUnique(out, item, max);
        continue;
      }
      if (item && typeof item === 'object' && !Array.isArray(item)) {
        const o = item as Record<string, unknown>;
        const segment = typeof o.segment === 'string' ? o.segment : typeof o.name === 'string' ? o.name : '';
        const bias = typeof o.bias === 'string' ? o.bias : typeof o.direction === 'string' ? o.direction : '';
        const conf = typeof o.confidence === 'string' ? o.confidence : '';
        const summary = typeof o.summary === 'string' ? o.summary : typeof o.note === 'string' ? o.note : '';
        const parts = [segment, bias, conf].filter(Boolean);
        if (parts.length) pushUnique(out, parts.join(' · '), max);
        else if (summary) pushUnique(out, summary, max);
      }
    }
  }

  if (out.length >= max) return out.slice(0, max);

  if (market_data && typeof market_data === 'object' && !Array.isArray(market_data)) {
    const md = market_data as Record<string, unknown>;
    for (const [k, v] of Object.entries(md)) {
      if (out.length >= max) break;
      if (typeof v === 'string' && v.trim()) {
        pushUnique(out, `${k}: ${v.trim()}`, max);
        continue;
      }
      if (v && typeof v === 'object' && !Array.isArray(v)) {
        const inner = v as Record<string, unknown>;
        const s =
          typeof inner.summary === 'string'
            ? inner.summary
            : typeof inner.label === 'string'
              ? inner.label
              : null;
        if (s?.trim()) pushUnique(out, `${k}: ${s.trim()}`, max);
      }
    }
  }

  return out.slice(0, max);
}
