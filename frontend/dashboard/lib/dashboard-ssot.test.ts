import { describe, expect, it } from 'vitest';
import {
  bookedCoversCommittedSnapshot,
  committedBookDate,
  previousBookDate,
  unpublishedBookNote,
} from './dashboard-ssot';

describe('committedBookDate', () => {
  it('ignores positions newer than the committed snapshot (uncommitted Monday book)', () => {
    expect(committedBookDate('2026-08-28', ['2026-08-31', '2026-08-28', '2026-08-27'])).toBe(
      '2026-08-28'
    );
  });

  it('returns null when the only positions are newer than the snapshot', () => {
    expect(committedBookDate('2026-08-28', ['2026-08-31'])).toBeNull();
  });

  it('returns null when there is no snapshot — never fall back to raw latest positions', () => {
    expect(committedBookDate(null, ['2026-08-31', '2026-08-28'])).toBeNull();
    expect(committedBookDate(undefined, ['2026-08-31'])).toBeNull();
  });

  it('uses the latest positions date on or before the snapshot when the snapshot date has no book', () => {
    expect(committedBookDate('2026-08-28', ['2026-08-27', '2026-08-26'])).toBe('2026-08-27');
  });
});

describe('previousBookDate', () => {
  it('picks the prior date strictly before the committed book, ignoring newer uncommitted rows', () => {
    expect(previousBookDate('2026-08-28', ['2026-08-31', '2026-08-28', '2026-08-27'])).toBe(
      '2026-08-27'
    );
  });
});

describe('bookedCoversCommittedSnapshot', () => {
  it('is false when latest positions are newer than the snapshot (the >= trap)', () => {
    expect(bookedCoversCommittedSnapshot('2026-08-28', '2026-08-31')).toBe(false);
  });

  it('is true only on an exact date match', () => {
    expect(bookedCoversCommittedSnapshot('2026-08-28', '2026-08-28')).toBe(true);
    expect(bookedCoversCommittedSnapshot('2026-08-28', '2026-08-27')).toBe(false);
    expect(bookedCoversCommittedSnapshot('2026-08-28', null)).toBe(false);
  });
});

describe('unpublishedBookNote', () => {
  it('explains a cancelled/uncommitted later run instead of looking like last week with no reason', () => {
    expect(unpublishedBookNote('2026-08-28', '2026-08-31')).toBe(
      'Last committed snapshot is 2026-08-28. Newer positions are hidden until a ledger commit lands.'
    );
  });

  it('is silent when the snapshot is today', () => {
    expect(unpublishedBookNote('2026-08-31', '2026-08-31')).toBeNull();
  });
});
