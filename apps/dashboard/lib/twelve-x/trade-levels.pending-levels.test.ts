/**
 * DIG-260 L5: the client never surfaces a half ladder.
 *
 * Authored by the EM before assignment. Frozen: the implementer makes these pass
 * and does not edit this file.
 *
 * The publish contract is that a bracket is published complete or not at all.
 * Until the producer is fully migrated a row can still arrive carrying a
 * populated shape with a non-complete status, and today `buildIdeaDetailModel`
 * derives ladder rows from the shape alone. A half bracket on screen reads as
 * actionable, which is the defect this leaf closes.
 *
 * These cases live in the pure model on purpose: `react` is not installed in
 * this checkout, so no render-level assertion could be verified before
 * assignment. The render-level work is specified in the leaf brief instead.
 */

import { describe, expect, it } from 'vitest';

import type { FxTradeIdeaRow } from '@/lib/twelve-x/types';
import { buildIdeaDetailModel } from '@/lib/twelve-x/trade-levels';

const SOURCE_REF = 'computed:vol20@2026-10-02|k=5.5|rr=1.5';

function level(value: string, provenance = 'computed') {
  return { value, provenance, source_ref: SOURCE_REF };
}

function ideaWith(levels: Record<string, unknown>): FxTradeIdeaRow {
  return {
    run_date: '2026-10-02',
    rank: 1,
    pair: 'EUR/USD',
    direction: 'long',
    title: 'EUR grind higher',
    thesis: 'Rate differential compression.',
    catalyst: 'ECB speakers',
    levels: [],
    citations: [{ source_file: 'beta/eurusd-note.md' }],
    as_of: '2026-10-02T10:00:00Z',
    trade_levels: levels as FxTradeIdeaRow['trade_levels'],
  };
}

/** The real production shape: a broker target survived, entry and stop did not. */
const BROKER_TARGET_ONLY = {
  targets: [{ value: '1.18', provenance: 'broker_quoted', source_ref: 'ING.pdf' }],
  risk_reward: null,
  status: 'partial',
};

/** Shape-complete but still labelled non-complete: the guard dropped nothing. */
const POPULATED_BUT_PARTIAL = {
  entry_low: level('1.15'),
  entry_high: level('1.16'),
  stop: level('1.14'),
  targets: [level('1.18')],
  risk_reward: 1.5,
  status: 'partial',
};

const POPULATED_BUT_INCOMPLETE = {
  entry_low: level('1.15'),
  entry_high: level('1.16'),
  stop: level('1.14'),
  targets: [level('1.18')],
  risk_reward: 1.5,
  status: 'incomplete',
};

const COMPLETE = {
  entry_low: level('1.15'),
  entry_high: level('1.16'),
  stop: level('1.14'),
  targets: [level('1.18')],
  risk_reward: 1.5,
  status: 'complete',
};

describe('DIG-260: a non-complete bracket yields no ladder', () => {
  it('a broker target alone is not a ladder', () => {
    expect(buildIdeaDetailModel(ideaWith(BROKER_TARGET_ONLY)).levelRows).toEqual([]);
  });

  it('a populated shape labelled partial is still not a ladder', () => {
    expect(buildIdeaDetailModel(ideaWith(POPULATED_BUT_PARTIAL)).levelRows).toEqual([]);
  });

  it('a populated shape labelled incomplete is still not a ladder', () => {
    expect(buildIdeaDetailModel(ideaWith(POPULATED_BUT_INCOMPLETE)).levelRows).toEqual([]);
  });

  it('a complete bracket still is one', () => {
    expect(buildIdeaDetailModel(ideaWith(COMPLETE)).levelRows.length).toBeGreaterThan(0);
  });

  it('risk/reward is not surfaced for a broker-target-only bracket', () => {
    expect(buildIdeaDetailModel(ideaWith(BROKER_TARGET_ONLY)).riskRewardLabel).toBeNull();
  });

  it('risk/reward is not surfaced for a populated but partial bracket', () => {
    expect(buildIdeaDetailModel(ideaWith(POPULATED_BUT_PARTIAL)).riskRewardLabel).toBeNull();
  });

  it('risk/reward is still surfaced for a complete bracket', () => {
    expect(buildIdeaDetailModel(ideaWith(COMPLETE)).riskRewardLabel).not.toBeNull();
  });
});
