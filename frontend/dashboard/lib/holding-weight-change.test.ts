import { describe, expect, it } from 'vitest';
import { readFileSync } from 'node:fs';
import { formatHoldingWeightChange, holdingWeightChange, holdingWeightDeltaPp } from './holding-weight-change';

/**
 * The owner's rule (#1850): show +/- for an add or a trim, but a brand-new or fully-removed
 * position has NO rate of change — it is just new, or gone.
 *
 * The bug this replaces: `weight - (prior ?? 0)` reported `+10.0pp` for a brand-new 10% position,
 * which reads as "added 10 points to an existing holding" rather than "opened a position".
 */
describe('holdingWeightChange', () => {
  it('reports no delta for a brand-new position', () => {
    const c = holdingWeightChange(10, null);
    expect(c.kind).toBe('new');
    expect(c.deltaPp).toBeNull(); // NOT +10
    expect(formatHoldingWeightChange(c)).toBeNull();
  });

  it('reports no delta for a fully-removed position', () => {
    const c = holdingWeightChange(null, 8.5);
    expect(c.kind).toBe('gone');
    expect(c.deltaPp).toBeNull(); // NOT -8.5
  });

  it('reports a decrease for a trim', () => {
    // The owner's example: 30% down to 15%.
    const c = holdingWeightChange(15, 30);
    expect(c.kind).toBe('decreased');
    expect(c.deltaPp).toBeCloseTo(-15, 6);
    expect(formatHoldingWeightChange(c)).toBe('-15.0pp');
  });

  it('reports an increase for an add', () => {
    // Real prod move: XRT 4.9207 → 10.0 on 2026-08-04.
    const c = holdingWeightChange(10.0, 4.9207);
    expect(c.kind).toBe('increased');
    expect(c.deltaPp).toBeCloseTo(5.0793, 4);
    expect(formatHoldingWeightChange(c)).toBe('+5.1pp');
  });

  it('reports the real prod trim', () => {
    // XLV 9.8616 → 5.0 on 2026-08-04.
    expect(formatHoldingWeightChange(holdingWeightChange(5.0, 9.8616))).toBe('-4.9pp');
  });

  it('treats a held-but-flat position as unchanged with no badge', () => {
    const c = holdingWeightChange(14.872, 14.872);
    expect(c.kind).toBe('unchanged');
    expect(c.deltaPp).toBe(0);
    expect(formatHoldingWeightChange(c)).toBeNull();
  });

  it('absorbs re-normalisation noise rather than calling it a decision', () => {
    // Weights are re-normalised to 100%, so a hold can drift by a hair.
    const c = holdingWeightChange(14.8721, 14.872);
    expect(c.kind).toBe('unchanged');
  });

  it('does NOT absorb a small but real move', () => {
    const c = holdingWeightChange(14.9, 14.872);
    expect(c.kind).toBe('increased');
  });

  it('distinguishes a 0% held sleeve from an absent one', () => {
    // 0% is held-and-flat (the CASH row does this) and CAN change; null is not held at all.
    // Conflating them is what produced the fabricated delta in the first place.
    expect(holdingWeightChange(5, 0).kind).toBe('increased');
    expect(holdingWeightChange(5, 0).deltaPp).toBeCloseTo(5, 6);
    expect(holdingWeightChange(5, null).kind).toBe('new');
    expect(holdingWeightChange(5, null).deltaPp).toBeNull();
  });

  it('says gone rather than unchanged when the row is absent on both dates', () => {
    // Never render "0.0pp" for something that is not in the book.
    const c = holdingWeightChange(null, null);
    expect(c.kind).toBe('gone');
    expect(c.deltaPp).toBeNull();
  });

  it('treats a non-finite weight as not held rather than as zero', () => {
    for (const bad of [NaN, Infinity, -Infinity, undefined]) {
      expect(holdingWeightChange(10, bad).kind).toBe('new');
      expect(holdingWeightChange(bad, 10).kind).toBe('gone');
    }
  });
});

describe('holdingWeightDeltaPp', () => {
  it('returns null for MTM drift when there was no material book event (#3080)', () => {
    expect(holdingWeightDeltaPp(15.16, 15.14, { hasMaterialBookEvent: false })).toBeNull();
  });

  it('keeps a material trim when the ledger recorded a decision', () => {
    expect(holdingWeightDeltaPp(5.0, 9.8616, { hasMaterialBookEvent: true })).toBeCloseTo(-4.8616, 4);
  });
});

/**
 * The call site, asserted on source shape.
 *
 * `queries.ts` is a large Supabase-fetching module with no test harness — which is precisely why
 * the `?? 0` bug lived there undetected. Extracting the pure function above covers the *logic*,
 * but a mutation test showed the call site is still unguarded: putting
 * `prevWeightByTicker.get(t) ?? 0` back breaks nothing, and the fabricated delta returns silently.
 *
 * So this pins the one expression that matters, the same way `test_pipeline_olympus_attempt.py`
 * pins the workflow's retry counter. It asserts the SHAPE (a `.has()` guard feeding a `null`, not
 * a `?? 0`) rather than an exact string, so a reasonable refactor still passes.
 */
describe('the queries.ts call site', () => {
  const source = (): string =>
    readFileSync(new URL('./queries.ts', import.meta.url), 'utf8');

  const weightDeltaBlock = (): string => {
    const src = source();
    const start = src.indexOf('weight_delta:');
    expect(start).toBeGreaterThan(-1);
    return src.slice(start, start + 400);
  };

  it('derives weight_delta through holdingWeightDeltaPp rather than inline arithmetic', () => {
    expect(weightDeltaBlock()).toContain('holdingWeightDeltaPp(');
  });

  it('does not coalesce a missing prior weight to zero', () => {
    // The bug verbatim: `prevWeightByTicker.get(p.ticker) ?? 0` makes a brand-new position
    // report its whole weight as a delta.
    expect(weightDeltaBlock()).not.toMatch(/prevWeightByTicker\.get\([^)]*\)\s*\?\?\s*0/);
  });

  it('distinguishes absent from zero with a .has() guard', () => {
    expect(weightDeltaBlock()).toContain('prevWeightByTicker.has(');
  });
});
