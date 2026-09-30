/**
 * Numeric level ladder for a trade idea: entry / stop / targets on one axis so
 * a RangeTrack can show where the levels sit relative to each other. Levels
 * arrive as display strings ("1.0850"); anything that does not parse to a
 * finite number is dropped, and an idea with fewer than two distinct levels
 * has no ladder (a single tick is not a range).
 */
import type { FxTradeIdeaRow } from './types';
import { parseTradeLevels } from './trade-levels';

export type LadderKind = 'entry' | 'stop' | 'target';

export interface LadderMarker {
  kind: LadderKind;
  value: number;
  label: string;
}

export interface IdeaLadder {
  low: number;
  high: number;
  markers: LadderMarker[];
}

/** Axis padding as a fraction of the level span so end markers do not sit on the rim. */
const PAD = 0.08;

export function parseLevelNumber(raw: string | null | undefined): number | null {
  if (typeof raw !== 'string') return null;
  const cleaned = raw.replace(/,/g, '').trim();
  if (cleaned === '') return null;
  const n = Number(cleaned);
  return Number.isFinite(n) ? n : null;
}

export function buildIdeaLadder(idea: Pick<FxTradeIdeaRow, 'trade_levels'>): IdeaLadder | null {
  const levels = parseTradeLevels(idea.trade_levels ?? null);
  if (!levels) return null;

  const markers: LadderMarker[] = [];
  const push = (kind: LadderKind, label: string, raw: string | undefined) => {
    const value = parseLevelNumber(raw);
    if (value !== null) markers.push({ kind, value, label });
  };

  const lowRaw = levels.entry_low?.value;
  const highRaw = levels.entry_high?.value;
  if (lowRaw !== undefined && highRaw !== undefined && lowRaw !== highRaw) {
    push('entry', 'Entry low', lowRaw);
    push('entry', 'Entry high', highRaw);
  } else {
    push('entry', 'Entry', lowRaw ?? highRaw);
  }
  push('stop', 'Stop', levels.stop?.value);
  levels.targets.forEach((t, i) => push('target', `Target ${i + 1}`, t.value));

  const values = markers.map((m) => m.value);
  const min = Math.min(...values);
  const max = Math.max(...values);
  if (markers.length < 2 || !(max > min)) return null;

  const pad = (max - min) * PAD;
  return { low: min - pad, high: max + pad, markers };
}

/** Text alternative: "Entry 1.085, Stop 1.07, Target 1 1.11". */
export function ladderSummary(ladder: IdeaLadder | null): string {
  if (!ladder) return 'No level ladder';
  return ladder.markers.map((m) => `${m.label} ${m.value}`).join(', ');
}
