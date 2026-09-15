import { describe, expect, it } from 'vitest';
import {
  annotateLevelUpdates,
  closeCounts,
  closeReason,
  displayableTradeHistory,
  tradeResult,
  type TradeHistoryRow,
} from './trade-history';

function row(partial: Partial<TradeHistoryRow>): TradeHistoryRow {
  return {
    runDate: '2026-09-01',
    rank: 1,
    pair: 'EUR/USD',
    direction: 'short',
    title: 'EUR/USD short',
    catalyst: '',
    entryBand: null,
    stop: null,
    target: null,
    hasLevels: false,
    lifecycle: 'closed',
    entryDate: null,
    exitDate: null,
    sessions: null,
    holdReturn: null,
    maxFavorable: null,
    maxAdverse: null,
    directionalWin: null,
    ...partial,
  };
}

describe('closeReason (Trades close column)', () => {
  it('labels level-touch closes from the level outcome', () => {
    expect(
      closeReason(
        row({ lifecycle: 'closed', levelOutcome: 'target', exitDate: '2026-09-05' }),
      ),
    ).toEqual({ kind: 'target', label: 'Target hit', detail: 'Closed 2026-09-05' });
    expect(closeReason(row({ lifecycle: 'closed', levelOutcome: 'stop' }))).toMatchObject({
      kind: 'stop',
      label: 'Stop hit',
    });
    expect(closeReason(row({ lifecycle: 'closed', levelOutcome: 'both' }))).toMatchObject({
      kind: 'both',
      label: 'Target + stop hit',
    });
  });

  it('calls a successor-clock close superseded', () => {
    const close = closeReason(row({ lifecycle: 'closed', exitDate: '2026-09-05' }));
    expect(close).toEqual({
      kind: 'superseded',
      label: 'Superseded by next board',
      detail: 'Superseded 2026-09-05',
    });
    expect(closeReason(row({ lifecycle: 'closed' })).detail).toBeUndefined();
  });

  it('surfaces the bookkeeper drop rationale', () => {
    expect(
      closeReason(
        row({ lifecycle: 'closed', evalStatus: 'dropped', verdictReason: 'thesis dead' }),
      ),
    ).toMatchObject({ kind: 'dropped', label: 'Dropped — thesis dead' });
    expect(
      closeReason(row({ lifecycle: 'closed', evalStatus: 'dropped' })).label,
    ).toBe('Dropped by bookkeeper');
  });

  it('marks live, no-data and unscored rows', () => {
    expect(closeReason(row({ lifecycle: 'live' }))).toEqual({ kind: 'live', label: 'Live' });
    expect(closeReason(row({ lifecycle: 'no_data' })).kind).toBe('no-data');
    expect(closeReason(row({ lifecycle: 'no_data' })).label).toBe('No data — missing rates');
    expect(closeReason(row({ lifecycle: 'unscored' })).label).toBe('Unscored');
  });

  it('calls a level band that never filled out as never filled', () => {
    expect(
      closeReason(
        row({ lifecycle: 'closed', levelOutcome: 'no_entry', exitDate: '2026-09-05' }),
      ),
    ).toEqual({
      kind: 'superseded',
      label: 'Never filled — superseded',
      detail: 'Superseded 2026-09-05',
    });
  });

  it('keeps a dropped row in the table as a closed result', () => {
    const dropped = row({
      lifecycle: 'closed',
      evalStatus: 'dropped',
      verdictReason: 'thesis dead',
    });
    expect(tradeResult(dropped)).toBe('closed');
    expect(displayableTradeHistory([dropped])).toHaveLength(1);
  });
});

describe('annotateLevelUpdates (updated while active)', () => {
  it('flags a live row whose stop or target moved since the previous board', () => {
    const older = row({
      runDate: '2026-09-01',
      lifecycle: 'live',
      stop: '1.1700',
      target: '1.1400',
    });
    const newer = row({
      runDate: '2026-09-05',
      lifecycle: 'live',
      stop: '1.1650',
      target: '1.1400',
    });
    const out = annotateLevelUpdates([newer, older]);
    const updated = out.find((r) => r.runDate === '2026-09-05')!;
    const untouched = out.find((r) => r.runDate === '2026-09-01')!;
    expect(updated.levelsUpdated).toBe(true);
    expect(updated.levelsUpdatedFrom).toBe('2026-09-01');
    expect(untouched.levelsUpdated).toBeUndefined();
  });

  it('leaves unchanged levels alone and never crosses directions', () => {
    const sameLevelsOlder = row({ runDate: '2026-09-01', lifecycle: 'live', stop: '1.1700' });
    const sameLevelsNewer = row({ runDate: '2026-09-05', lifecycle: 'live', stop: '1.1700' });
    expect(
      annotateLevelUpdates([sameLevelsOlder, sameLevelsNewer]).every(
        (r) => r.levelsUpdated === undefined,
      ),
    ).toBe(true);

    const shortOlder = row({ runDate: '2026-09-01', lifecycle: 'live', stop: '1.1700' });
    const longNewer = row({
      runDate: '2026-09-05',
      lifecycle: 'live',
      direction: 'long',
      stop: '1.1600',
    });
    expect(
      annotateLevelUpdates([shortOlder, longNewer]).every((r) => r.levelsUpdated === undefined),
    ).toBe(true);
  });

  it('treats the reversed orientation of the same axis as the same position', () => {
    const older = row({
      runDate: '2026-09-01',
      pair: 'EUR/USD',
      direction: 'short',
      lifecycle: 'live',
      stop: '1.1700',
    });
    const newer = row({
      runDate: '2026-09-05',
      pair: 'USD/EUR',
      direction: 'long',
      lifecycle: 'live',
      stop: '1.1650',
    });
    const out = annotateLevelUpdates([older, newer]);
    expect(out.find((r) => r.runDate === '2026-09-05')?.levelsUpdated).toBe(true);
    expect(out.find((r) => r.runDate === '2026-09-05')?.levelsUpdatedFrom).toBe('2026-09-01');
  });
});

describe('closeCounts (close-reason tally)', () => {
  it('tallies each close kind across closed, no-data and live rows', () => {
    const counts = closeCounts([
      row({ rank: 1, lifecycle: 'closed', levelOutcome: 'target' }),
      row({ rank: 2, lifecycle: 'closed', levelOutcome: 'stop' }),
      row({ rank: 3, lifecycle: 'closed', levelOutcome: 'both' }),
      row({ rank: 4, lifecycle: 'closed' }),
      row({ rank: 5, lifecycle: 'closed', evalStatus: 'dropped', verdictReason: 'done' }),
      row({ rank: 6, lifecycle: 'no_data' }),
      row({ rank: 7, lifecycle: 'live' }),
    ]);
    expect(counts).toMatchObject({
      targets: 1,
      stops: 1,
      both: 1,
      superseded: 1,
      dropped: 1,
      noData: 1,
      live: 1,
    });
  });
});
