import { describe, expect, it } from 'vitest';
import { buildIdeaLadder, ladderSummary, parseLevelNumber } from './idea-ladder';

const lvl = (value: string) => ({ value, provenance: 'broker_quoted', source_ref: '' });

describe('parseLevelNumber', () => {
  it('parses plain and comma-grouped numbers and rejects junk', () => {
    expect(parseLevelNumber('1.0850')).toBeCloseTo(1.085);
    expect(parseLevelNumber('1,950')).toBe(1950);
    expect(parseLevelNumber('n/a')).toBeNull();
    expect(parseLevelNumber(undefined)).toBeNull();
  });
});

describe('buildIdeaLadder', () => {
  it('places entry, stop and targets on one padded axis', () => {
    const ladder = buildIdeaLadder({
      trade_levels: {
        entry_low: lvl('1.0850'),
        entry_high: null,
        stop: lvl('1.0700'),
        targets: [lvl('1.1100'), lvl('1.1250')],
        risk_reward: 1.7,
        status: 'complete',
      },
    });
    expect(ladder).not.toBeNull();
    expect(ladder!.markers.map((m) => m.kind)).toEqual(['entry', 'stop', 'target', 'target']);
    expect(ladder!.low).toBeLessThan(1.07);
    expect(ladder!.high).toBeGreaterThan(1.125);
    expect(ladderSummary(ladder)).toBe('Entry 1.085, Stop 1.07, Target 1 1.11, Target 2 1.125');
  });

  it('draws both ends of an entry zone', () => {
    const ladder = buildIdeaLadder({
      trade_levels: {
        entry_low: lvl('150.0'),
        entry_high: lvl('151.0'),
        stop: lvl('148.0'),
        targets: [],
        risk_reward: null,
        status: 'partial',
      },
    });
    expect(ladder!.markers.filter((m) => m.kind === 'entry')).toHaveLength(2);
  });

  it('has no ladder with a single level, missing levels, or unparseable values', () => {
    expect(buildIdeaLadder({ trade_levels: null })).toBeNull();
    expect(buildIdeaLadder({ trade_levels: {} })).toBeNull();
    expect(
      buildIdeaLadder({
        trade_levels: { entry_low: lvl('1.1'), entry_high: null, stop: null, targets: [], risk_reward: null, status: 'partial' },
      }),
    ).toBeNull();
    expect(
      buildIdeaLadder({
        trade_levels: { entry_low: lvl('abc'), entry_high: null, stop: lvl('1.0'), targets: [], risk_reward: null, status: 'partial' },
      }),
    ).toBeNull();
    expect(ladderSummary(null)).toBe('No level ladder');
  });
});
