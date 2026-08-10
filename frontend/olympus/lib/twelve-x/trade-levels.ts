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

/** Trim trailing zeros for display while preserving significant decimals. */
export function formatLevelValue(value: string): string {
  const trimmed = value.trim();
  if (!trimmed.includes('.')) return trimmed;
  return trimmed.replace(/(\.\d*?)0+$/, '$1').replace(/\.$/, '');
}

export interface IdeaDetailLevelRow {
  label: string;
  value: string;
  chip: string;
}

export interface IdeaDetailEvidenceRow {
  statement: string;
  stance: FxMarketEvidence['stance'];
  className: string;
}

export interface IdeaDetailModel {
  status: FxTradeLevels['status'] | null;
  riskReward: number | null;
  levelRows: IdeaDetailLevelRow[];
  evidenceRows: IdeaDetailEvidenceRow[];
}

function entryLevelRow(
  entry_low: FxTradeLevel | null,
  entry_high: FxTradeLevel | null,
): IdeaDetailLevelRow | null {
  if (!entry_low && !entry_high) return null;

  if (entry_low && entry_high) {
    const chipLow = provenanceChipLabel(entry_low);
    const chipHigh = provenanceChipLabel(entry_high);
    const chip = chipLow === chipHigh ? chipLow : `${chipLow} · ${chipHigh}`;
    return {
      label: 'Entry',
      value: `${formatLevelValue(entry_low.value)}–${formatLevelValue(entry_high.value)}`,
      chip,
    };
  }

  const level = entry_low ?? entry_high;
  if (!level) return null;
  return {
    label: 'Entry',
    value: formatLevelValue(level.value),
    chip: provenanceChipLabel(level),
  };
}

/** Pure view-model for IdeaDetail levels + evidence blocks. */
export function buildIdeaDetailModel(idea: FxTradeIdeaRow): IdeaDetailModel {
  const tradeLevels = parseTradeLevels(idea.trade_levels);
  const levelRows: IdeaDetailLevelRow[] = [];

  if (hasTradeLevels(tradeLevels)) {
    const entry = entryLevelRow(tradeLevels!.entry_low, tradeLevels!.entry_high);
    if (entry) levelRows.push(entry);

    if (tradeLevels!.stop) {
      levelRows.push({
        label: 'Stop',
        value: formatLevelValue(tradeLevels!.stop.value),
        chip: provenanceChipLabel(tradeLevels!.stop),
      });
    }

    tradeLevels!.targets.forEach((target, index) => {
      levelRows.push({
        label: index === 0 ? 'Target' : `Target ${index + 1}`,
        value: formatLevelValue(target.value),
        chip: provenanceChipLabel(target),
      });
    });
  }

  const evidenceRows = parseEvidence(idea.evidence).map((row) => ({
    statement: row.statement,
    stance: row.stance,
    className: evidenceStanceClass(row.stance),
  }));

  return {
    status: tradeLevels?.status ?? null,
    riskReward: tradeLevels?.risk_reward ?? null,
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
