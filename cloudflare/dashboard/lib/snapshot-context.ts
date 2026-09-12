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

// ─── Body → Brief DTO adapter (#3641) ───────────────────────────────────────
// Phase 7 stitch-to-body drops structured `headline` / `actionable_summary` /
// `risk_radar` from daily_snapshots.snapshot. The same content still lives under
// `## Headline`, `## Watchlist`, and `## Risk radar` in `body`. Parse once here;
// structured JSON wins when present.

/** Strip a single layer of surrounding `**…**` markdown bold. */
function stripOuterBold(s: string): string {
  const t = s.trim();
  const m = t.match(/^\*\*(.+)\*\*$/);
  return m ? m[1]!.trim() : t;
}

/**
 * Text under `## Heading` until the next `## ` line (or EOF).
 * Heading match is case-insensitive; leading/trailing whitespace ignored.
 */
export function extractMarkdownH2Section(body: string, heading: string): string {
  if (!body || typeof body !== 'string') return '';
  const want = heading.trim().toLowerCase();
  const lines = body.split(/\r?\n/);
  let start = -1;
  for (let i = 0; i < lines.length; i++) {
    const m = lines[i]!.match(/^##\s+(.+?)\s*$/);
    if (!m) continue;
    if (m[1]!.trim().toLowerCase() === want) {
      start = i + 1;
      break;
    }
  }
  if (start < 0) return '';
  const out: string[] = [];
  for (let i = start; i < lines.length; i++) {
    if (/^##\s+/.test(lines[i]!)) break;
    out.push(lines[i]!);
  }
  return out.join('\n').trim();
}

/** First non-empty paragraph under `## Headline`. */
export function parseHeadlineFromDigestBody(body: string): string | null {
  const section = extractMarkdownH2Section(body, 'Headline');
  if (!section) return null;
  const para = section
    .split(/\n\s*\n/)
    .map((p) => p.replace(/\s+/g, ' ').trim())
    .find((p) => p.length > 0);
  return para || null;
}

/** Bullet lines under a section (`- …` or `* …`). */
function sectionBulletLines(section: string): string[] {
  const out: string[] = [];
  for (const raw of section.split(/\r?\n/)) {
    const m = raw.match(/^\s*[-*]\s+(.+)$/);
    if (m?.[1]?.trim()) out.push(m[1].trim());
  }
  return out;
}

/**
 * Split `label — detail` on an em/en dash or spaced hyphen. Prefer the first
 * em/en dash; fall back to ` - ` / ` -- `.
 */
function splitLabelDetail(text: string): { label: string; detail: string | null } {
  const em = text.match(/^(.+?)\s*[—–]\s*(.+)$/);
  if (em) return { label: em[1]!.trim(), detail: em[2]!.trim() || null };
  const hyphen = text.match(/^(.+?)\s+--?\s+(.+)$/);
  if (hyphen) return { label: hyphen[1]!.trim(), detail: hyphen[2]!.trim() || null };
  return { label: text.trim(), detail: null };
}

/**
 * Watchlist bullets → ActionableItem[].
 * Accepts stitcher / legacy shapes:
 *   - **[P1] Monitor DXY above 104** — near YTD highs
 *   - [P2] Watch semis breadth — AI capex commentary into earnings
 *   - **Bare label** — rationale only
 */
export function parseWatchlistFromDigestBody(body: string): ActionableItem[] {
  const section = extractMarkdownH2Section(body, 'Watchlist');
  if (!section) return [];
  const out: ActionableItem[] = [];
  for (const bullet of sectionBulletLines(section)) {
    let rest = stripOuterBold(bullet);
    // Also unwrap bold that only wraps the `[P#] label` prefix.
    rest = rest.replace(/^\*\*(.+?)\*\*/, '$1').trim();
    let priority: number | null = null;
    const pri = rest.match(/^\[P(\d+)\]\s*(.*)$/i);
    if (pri) {
      priority = Number(pri[1]);
      rest = pri[2]!.trim();
    } else {
      const priLoose = rest.match(/^P(\d+)\s+(.+)$/i);
      if (priLoose) {
        priority = Number(priLoose[1]);
        rest = priLoose[2]!.trim();
      }
    }
    rest = stripOuterBold(rest);
    const { label, detail } = splitLabelDetail(rest);
    const cleanLabel = stripOuterBold(label);
    if (!cleanLabel) continue;
    out.push({
      label: cleanLabel,
      priority: Number.isFinite(priority as number) ? priority : null,
      rationale: detail ? stripOuterBold(detail) : null,
    });
  }
  return out.sort((a, b) => {
    if (a.priority == null && b.priority == null) return 0;
    if (a.priority == null) return 1;
    if (b.priority == null) return -1;
    return a.priority - b.priority;
  });
}

/**
 * Risk radar bullets → RiskItem[].
 * Accepts:
 *   - **BOJ intervention** — USD/JPY break above 162 _(≤48h)_
 *   - CPI surprise — hotter core _(<=24h)_
 */
export function parseRiskRadarFromDigestBody(body: string): RiskItem[] {
  const section =
    extractMarkdownH2Section(body, 'Risk radar') ||
    extractMarkdownH2Section(body, 'Risk Radar');
  if (!section) return [];
  const out: RiskItem[] = [];
  for (const bullet of sectionBulletLines(section)) {
    let rest = stripOuterBold(bullet);
    rest = rest.replace(/^\*\*(.+?)\*\*/, '$1').trim();
    let horizonHours: number | null = null;
    const hz = rest.match(/_\(≤\s*(\d+)\s*h\)_\s*$/i) || rest.match(/_\(<=\s*(\d+)\s*h\)_\s*$/i);
    if (hz) {
      horizonHours = Number(hz[1]);
      rest = rest.slice(0, hz.index).trim();
    }
    rest = stripOuterBold(rest);
    const { label, detail } = splitLabelDetail(rest);
    const cleanLabel = stripOuterBold(label);
    if (!cleanLabel) continue;
    out.push({
      label: cleanLabel,
      trigger: detail ? stripOuterBold(detail) : null,
      horizonHours: Number.isFinite(horizonHours as number) ? horizonHours : null,
    });
  }
  return out;
}

export type BriefFieldsFromDigest = {
  headline: string | null;
  actionableItems: ActionableItem[];
  riskItems: RiskItem[];
  actionable: string[];
  risks: string[];
};

/**
 * SSOT Brief DTO resolve: structured snapshot fields win when non-empty;
 * otherwise derive from stitched markdown `body` (`## Headline` / `## Watchlist` /
 * `## Risk radar`). Call at the query/snapshot boundary so Brief consumers stay
 * unchanged.
 */
export function resolveBriefFieldsFromDigest(digest: unknown): BriefFieldsFromDigest {
  const d =
    digest && typeof digest === 'object' && !Array.isArray(digest)
      ? (digest as Record<string, unknown>)
      : {};
  const body = typeof d.body === 'string' ? d.body : '';

  const structuredHeadline =
    typeof d.headline === 'string' && d.headline.trim() ? d.headline.trim() : null;
  const headline = structuredHeadline ?? parseHeadlineFromDigestBody(body);

  const structuredActionables = parseActionableItems(d.actionable_summary);
  const actionableItems =
    structuredActionables.length > 0
      ? structuredActionables
      : parseWatchlistFromDigestBody(body);

  const structuredRisks = parseRiskItems(d.risk_radar);
  const riskItems =
    structuredRisks.length > 0 ? structuredRisks : parseRiskRadarFromDigestBody(body);

  return {
    headline,
    actionableItems,
    riskItems,
    actionable:
      structuredActionables.length > 0
        ? digestItemsToStrings(d.actionable_summary)
        : actionableItems.map((a) =>
            [a.label, a.rationale].filter(Boolean).join(' — '),
          ),
    risks:
      structuredRisks.length > 0
        ? digestItemsToStrings(d.risk_radar)
        : riskItems.map((r) => [r.label, r.trigger].filter(Boolean).join(' — ')),
  };
}
