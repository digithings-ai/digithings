/**
 * Context bullets + digest list normalization for Overview / Strategy footnotes,
 * read from the `daily_snapshots.snapshot` JSONB digest. The legacy flat
 * segment_biases / market_data columns (and their extractor) were dropped in #714.
 */

import type { ActionableItem, RiskItem } from './types';

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

/**
 * Structured parse of `actionable_summary` ActionableItem[] (label/priority/rationale),
 * sorted by priority ascending (the pipeline's own ranking — F5-permitted numbering),
 * nulls last. Plain-string entries degrade to a bare label. Non-arrays → [].
 */
export function parseActionableItems(items: unknown): ActionableItem[] {
  if (!Array.isArray(items)) return [];
  const out: ActionableItem[] = [];
  for (const item of items) {
    if (typeof item === 'string') {
      const t = item.trim();
      if (t) out.push({ label: t, priority: null, rationale: null });
      continue;
    }
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const o = item as Record<string, unknown>;
      const label = typeof o.label === 'string' ? o.label.trim() : '';
      if (!label) continue;
      out.push({
        label,
        priority: typeof o.priority === 'number' ? o.priority : null,
        rationale: typeof o.rationale === 'string' && o.rationale.trim() ? o.rationale.trim() : null,
      });
    }
  }
  return out.sort((a, b) => {
    if (a.priority == null && b.priority == null) return 0;
    if (a.priority == null) return 1;
    if (b.priority == null) return -1;
    return a.priority - b.priority;
  });
}

/**
 * Structured parse of `risk_radar` RiskItem[] (label/trigger/horizon_hours), input order
 * preserved (the pipeline orders by salience). Plain strings degrade to a bare label.
 */
export function parseRiskItems(items: unknown): RiskItem[] {
  if (!Array.isArray(items)) return [];
  const out: RiskItem[] = [];
  for (const item of items) {
    if (typeof item === 'string') {
      const t = item.trim();
      if (t) out.push({ label: t, trigger: null, horizonHours: null });
      continue;
    }
    if (item && typeof item === 'object' && !Array.isArray(item)) {
      const o = item as Record<string, unknown>;
      const label = typeof o.label === 'string' ? o.label.trim() : '';
      if (!label) continue;
      out.push({
        label,
        trigger: typeof o.trigger === 'string' && o.trigger.trim() ? o.trigger.trim() : null,
        horizonHours: typeof o.horizon_hours === 'number' ? o.horizon_hours : null,
      });
    }
  }
  return out;
}
