import { describe, expect, it } from 'vitest';
import { parsePhaseHealth } from './run-phase-health';

const breakdown = {
  phase1_outputs: { ok: 5, failed: 0, carried: 1 },
  phase2_outputs: { ok: 2, failed: 0, carried: 0 },
  phase3_output: { ok: 1, failed: 0, carried: 0 }, // singular in live data
  phase4_outputs: { ok: 3, failed: 0, carried: 2 },
  phase5_outputs: { ok: 8, failed: 0, carried: 5 },
  cached_tokens: 2028160,
  by_kind: {},
};

describe('parsePhaseHealth', () => {
  it('extracts phases 1–5 in numeric order, accepting singular phase3_output', () => {
    const phases = parsePhaseHealth(breakdown);
    expect(phases.map((p) => p.phase)).toEqual([1, 2, 3, 4, 5]);
    expect(phases[0]).toMatchObject({ phase: 1, ok: 5, carried: 1, failed: 0 });
    expect(phases[2]).toMatchObject({ phase: 3, ok: 1 });
  });
  it('returns [] for null/non-object breakdown', () => {
    expect(parsePhaseHealth(null)).toEqual([]);
    expect(parsePhaseHealth({ by_kind: {} })).toEqual([]);
  });
  it('ignores non-phase keys', () => {
    expect(parsePhaseHealth({ cached_tokens: 1, models: [] })).toEqual([]);
  });
});
