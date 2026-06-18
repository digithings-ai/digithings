/**
 * Context bullets + digest list normalization for Overview / Strategy footnotes,
 * read from the `daily_snapshots.snapshot` JSONB digest. The legacy flat
 * segment_biases / market_data columns (and their extractor) were dropped in #714.
 */

function pushUnique(out: string[], line: string, max: number) {
  const t = line.trim();
  if (!t || out.length >= max) return;
  if (out.includes(t)) return;
  out.push(t.length > 160 ? `${t.slice(0, 157)}…` : t);
}

/** Narrative sections of the pipeline digest payload used as Overview context bullets. */
const DIGEST_BULLET_SECTIONS: Array<[key: string, label: string]> = [
  ['us_equities_summary', 'US equities'],
  ['asset_classes_summary', 'Asset classes'],
  ['institutional_summary', 'Institutional'],
  ['alt_data_dashboard', 'Alt-data'],
];

/**
 * Context bullets from the pipeline digest (`daily_snapshots.snapshot` JSONB)
 * for snapshots where the legacy `segment_biases` / `market_data` columns are
 * null (every SIMP-013 pipeline row).
 */
export function extractDigestContextBullets(digest: unknown, max = 5): string[] {
  const out: string[] = [];
  if (!digest || typeof digest !== 'object' || Array.isArray(digest)) return out;
  const d = digest as Record<string, unknown>;
  for (const [key, label] of DIGEST_BULLET_SECTIONS) {
    if (out.length >= max) break;
    const v = d[key];
    if (typeof v === 'string' && v.trim()) pushUnique(out, `${label}: ${v.trim()}`, max);
  }
  return out.slice(0, max);
}

/**
 * Normalize digest list entries (`actionable_summary` ActionableItem[] /
 * `risk_radar` RiskItem[], or plain strings) to display strings.
 */
export function digestItemsToStrings(items: unknown): string[] {
  if (!Array.isArray(items)) return [];
  const out: string[] = [];
  for (const item of items) {
    if (typeof item === 'string') {
      if (item.trim()) out.push(item.trim());
      continue;
    }
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const o = item as Record<string, unknown>;
      const label = typeof o.label === 'string' ? o.label.trim() : '';
      const detail =
        typeof o.rationale === 'string'
          ? o.rationale.trim()
          : typeof o.trigger === 'string'
            ? o.trigger.trim()
            : typeof o.summary === 'string'
              ? o.summary.trim()
              : '';
      const text = [label, detail].filter(Boolean).join(' — ');
      if (text) out.push(text);
    }
  }
  return out;
}
