/**
 * Pure parsers and formatters for trade_levels / evidence jsonb on trade ideas.
 */
import type {
  FxLevelProvenance,
  FxMarketEvidence,
  FxTradeIdeaRow,
  FxTradeLevel,
  FxTradeLevels,
} from './types';

const PROVENANCES: readonly FxLevelProvenance[] = [
  'broker_quoted',
  'pmt_bank_trade',
  'pmt_seasonality_target',
  'pmt_position_cluster',
  'computed',
];

const STATUSES: readonly FxTradeLevels['status'][] = ['complete', 'partial', 'incomplete'];

const STANCES: readonly FxMarketEvidence['stance'][] = ['supports', 'contradicts', 'context'];

const MONTH_ABBREV = ['Jan', 'Feb', 'Mar', 'Apr', 'May', 'Jun', 'Jul', 'Aug', 'Sep', 'Oct', 'Nov', 'Dec'];

const COMPUTED_REF_RE = /^computed:vol(\d+)@(\d{4}-\d{2}-\d{2})\|k=([^|]+)\|rr=/;

/** Provenances that keep broker-presented precision (trim zeros only). */
const PRESENTED_PRECISION: ReadonlySet<FxLevelProvenance> = new Set([
  'broker_quoted',
  'pmt_bank_trade',
  'pmt_seasonality_target',
  'pmt_position_cluster',
]);

function isProvenance(value: unknown): value is FxLevelProvenance {
  return typeof value === 'string' && (PROVENANCES as readonly string[]).includes(value);
}

function isStatus(value: unknown): value is FxTradeLevels['status'] {
  return typeof value === 'string' && (STATUSES as readonly string[]).includes(value);
}

function isStance(value: unknown): value is FxMarketEvidence['stance'] {
  return typeof value === 'string' && (STANCES as readonly string[]).includes(value);
}

function parseTradeLevel(raw: unknown): FxTradeLevel | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  const value =
    typeof o.value === 'string'
      ? o.value
      : typeof o.value === 'number' && Number.isFinite(o.value)
        ? String(o.value)
        : null;
  if (!value || !isProvenance(o.provenance)) return null;
  return {
    value,
    provenance: o.provenance,
    source_ref: typeof o.source_ref === 'string' ? o.source_ref : '',
  };
}

function parseTradeLevelArray(raw: unknown): FxTradeLevel[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    const level = parseTradeLevel(item);
    return level ? [level] : [];
  });
}

/** Parse trade_levels jsonb; null when missing, empty, or has no level slots. */
export function parseTradeLevels(raw: unknown): FxTradeLevels | null {
  if (raw == null) return null;
  if (typeof raw !== 'object' || Array.isArray(raw)) return null;

  const o = raw as Record<string, unknown>;
  if (Object.keys(o).length === 0) return null;

  const entry_low = parseTradeLevel(o.entry_low);
  const entry_high = parseTradeLevel(o.entry_high);
  const stop = parseTradeLevel(o.stop);
  const targets = parseTradeLevelArray(o.targets);

  if (!entry_low && !entry_high && !stop && targets.length === 0) return null;

  const risk_reward =
    typeof o.risk_reward === 'number' && Number.isFinite(o.risk_reward) ? o.risk_reward : null;

  return {
    entry_low,
    entry_high,
    stop,
    targets,
    risk_reward,
    status: isStatus(o.status) ? o.status : 'incomplete',
  };
}

/** True when any entry, stop, or target slot is populated. */
export function hasTradeLevels(tl: FxTradeLevels | null): boolean {
  if (!tl) return false;
  return Boolean(tl.entry_low || tl.entry_high || tl.stop || tl.targets.length > 0);
}

function parseEvidenceRow(raw: unknown): FxMarketEvidence | null {
  if (!raw || typeof raw !== 'object' || Array.isArray(raw)) return null;
  const o = raw as Record<string, unknown>;
  if (
    typeof o.source_slug !== 'string' ||
    typeof o.instrument !== 'string' ||
    typeof o.as_of !== 'string' ||
    typeof o.statement !== 'string' ||
    typeof o.snapshot_id !== 'string' ||
    !isStance(o.stance)
  ) {
    return null;
  }
  return {
    source_slug: o.source_slug,
    instrument: o.instrument,
    as_of: o.as_of,
    statement: o.statement,
    stance: o.stance,
    snapshot_id: o.snapshot_id,
  };
}

/** Parse evidence jsonb array; empty when missing or invalid. */
export function parseEvidence(raw: unknown): FxMarketEvidence[] {
  if (!Array.isArray(raw)) return [];
  return raw.flatMap((item) => {
    const row = parseEvidenceRow(item);
    return row ? [row] : [];
  });
}

function basenameStem(sourceRef: string): string {
  const base = sourceRef.split(/[/\\]/).pop() ?? '';
  const dot = base.lastIndexOf('.');
  const stem = dot > 0 ? base.slice(0, dot) : base;
  return stem.replace(/[_-]+/g, ' ').trim();
}

function formatComputedFixDate(isoDate: string): string | null {
  const match = /^(\d{4})-(\d{2})-(\d{2})$/.exec(isoDate);
  if (!match) return null;
  const year = Number(match[1]);
  const month = Number(match[2]);
  const day = Number(match[3]);
  const utc = new Date(Date.UTC(year, month - 1, day));
  if (
    utc.getUTCFullYear() !== year ||
    utc.getUTCMonth() !== month - 1 ||
    utc.getUTCDate() !== day
  ) {
    return null;
  }
  const monthLabel = MONTH_ABBREV[utc.getUTCMonth()];
  return `${utc.getUTCDate()} ${monthLabel}`;
}

/** Human-readable provenance chip label for a level. */
export function provenanceChipLabel(level: FxTradeLevel): string {
  switch (level.provenance) {
    case 'broker_quoted': {
      const stem = basenameStem(level.source_ref);
      return stem ? `${stem} target` : 'broker target';
    }
    case 'computed': {
      const match = COMPUTED_REF_RE.exec(level.source_ref);
      if (!match) return 'computed';
      const [, volDays, isoDate, k] = match;
      const fixDate = formatComputedFixDate(isoDate);
      if (!fixDate) return 'computed';
      return `computed, ${k}×${volDays}d vol off ${fixDate} fix`;
    }
    case 'pmt_bank_trade':
      return 'bank trade';
    case 'pmt_seasonality_target':
      return 'seasonality';
    case 'pmt_position_cluster':
      return 'position book';
    default: {
      const _exhaustive: never = level.provenance;
      return _exhaustive;
    }
  }
}

/** Pair-reasonable decimals for computed levels (JPY crosses ~3, majors ~5). */
export function pairPriceDecimals(pair: string): number {
  const p = pair.trim().toUpperCase();
  if (p.includes('JPY')) return 3;
  return 5;
}

function trimTrailingZeros(value: string): string {
  if (!value.includes('.')) return value;
  return value.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
}

/**
 * Format a level for display.
 * Broker-presented: keep precision, trim junk trailing zeros.
 * Computed (with pair): round to pair-reasonable decimals, then trim zeros.
 */
export function formatLevelValue(
  value: string,
  pair?: string,
  provenance?: FxLevelProvenance,
): string {
  const trimmed = value.trim();
  if (!trimmed) return trimmed;

  const keepPresented =
    !provenance || PRESENTED_PRECISION.has(provenance) || !pair || !pair.trim();

  if (keepPresented) {
    return trimTrailingZeros(trimmed);
  }

  const n = Number(trimmed);
  if (!Number.isFinite(n)) return trimTrailingZeros(trimmed);
  const decimals = pairPriceDecimals(pair);
  return trimTrailingZeros(n.toFixed(decimals));
}

/** R:R display — one decimal. */
export function formatRiskReward(rr: number): string {
  if (!Number.isFinite(rr)) return String(rr);
  return (Math.round(rr * 10) / 10).toFixed(1);
}

export type IdeaDetailLevelRole = 'entry' | 'stop' | 'target';

export interface IdeaDetailLevelRow {
  label: string;
  value: string;
  chip: string;
  role: IdeaDetailLevelRole;
}

export interface IdeaDetailEvidenceRow {
  statement: string;
  stance: FxMarketEvidence['stance'];
  className: string;
}

export interface IdeaDetailModel {
  status: FxTradeLevels['status'] | null;
  riskReward: number | null;
  riskRewardLabel: string | null;
  levelRows: IdeaDetailLevelRow[];
  evidenceRows: IdeaDetailEvidenceRow[];
}

function formatEntryValue(
  entry_low: FxTradeLevel | null,
  entry_high: FxTradeLevel | null,
  pair: string,
): { value: string; chip: string } | null {
  if (!entry_low && !entry_high) return null;

  if (entry_low && entry_high) {
    const chipLow = provenanceChipLabel(entry_low);
    const chipHigh = provenanceChipLabel(entry_high);
    const chip = chipLow === chipHigh ? chipLow : `${chipLow} · ${chipHigh}`;
    return {
      value: `${formatLevelValue(entry_low.value, pair, entry_low.provenance)}–${formatLevelValue(entry_high.value, pair, entry_high.provenance)}`,
      chip,
    };
  }

  const level = entry_low ?? entry_high;
  if (!level) return null;
  return {
    value: formatLevelValue(level.value, pair, level.provenance),
    chip: provenanceChipLabel(level),
  };
}

function isLongDirection(direction: string): boolean {
  const d = direction.trim().toLowerCase();
  return d.includes('long') || d.includes('bull');
}

/**
 * Build ladder rows in price-descending visual order:
 * long → Target, Entry, Stop; short → Stop, Entry, Target.
 * Semantic colors stay role-based (target accent, stop warn) regardless of order.
 */
function buildLadderRows(
  tradeLevels: FxTradeLevels,
  pair: string,
  direction: string,
): IdeaDetailLevelRow[] {
  const entry = formatEntryValue(tradeLevels.entry_low, tradeLevels.entry_high, pair);
  const entryRow: IdeaDetailLevelRow | null = entry
    ? { label: 'Entry', value: entry.value, chip: entry.chip, role: 'entry' }
    : null;

  const stopRow: IdeaDetailLevelRow | null = tradeLevels.stop
    ? {
        label: 'Stop',
        value: formatLevelValue(tradeLevels.stop.value, pair, tradeLevels.stop.provenance),
        chip: provenanceChipLabel(tradeLevels.stop),
        role: 'stop',
      }
    : null;

  // Multi-target ladder: price-descending for display (labels follow display order).
  const targetsByPriceDesc = [...tradeLevels.targets].sort((a, b) => {
    const na = Number(a.value);
    const nb = Number(b.value);
    if (Number.isFinite(na) && Number.isFinite(nb)) return nb - na;
    return 0;
  });
  const targetRows: IdeaDetailLevelRow[] = targetsByPriceDesc.map((target, index) => ({
    label: index === 0 ? 'Target' : `Target ${index + 1}`,
    value: formatLevelValue(target.value, pair, target.provenance),
    chip: provenanceChipLabel(target),
    role: 'target',
  }));

  const long = isLongDirection(direction);
  const rows: IdeaDetailLevelRow[] = [];
  if (long) {
    rows.push(...targetRows);
    if (entryRow) rows.push(entryRow);
    if (stopRow) rows.push(stopRow);
  } else {
    if (stopRow) rows.push(stopRow);
    if (entryRow) rows.push(entryRow);
    rows.push(...targetRows);
  }
  return rows;
}

/** Pure view-model for IdeaDetail levels + evidence blocks. */
export function buildIdeaDetailModel(idea: FxTradeIdeaRow): IdeaDetailModel {
  const tradeLevels = parseTradeLevels(idea.trade_levels);
  const levelRows =
    hasTradeLevels(tradeLevels) && tradeLevels
      ? buildLadderRows(tradeLevels, idea.pair, idea.direction)
      : [];

  const evidenceRows = parseEvidence(idea.evidence).map((row) => ({
    statement: row.statement,
    stance: row.stance,
    className: evidenceStanceClass(row.stance),
  }));

  const riskReward = tradeLevels?.risk_reward ?? null;

  return {
    status: tradeLevels?.status ?? null,
    riskReward,
    riskRewardLabel: riskReward != null ? formatRiskReward(riskReward) : null,
    levelRows,
    evidenceRows,
  };
}

/** Tailwind text color class for an evidence stance. */
export function evidenceStanceClass(stance: FxMarketEvidence['stance']): string {
  switch (stance) {
    case 'supports':
      return 'text-accent';
    case 'contradicts':
      return 'text-warn';
    case 'context':
      return 'text-ink-mute';
    default: {
      const _exhaustive: never = stance;
      return _exhaustive;
    }
  }
}
