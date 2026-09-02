import { describe, expect, it } from 'vitest';
import {
  assertDailySnapshotQueryOk,
  bookedCoversCommittedSnapshot,
  committedBookDate,
  previousBookDate,
  unpublishedBookNote,
} from './dashboard-ssot';

describe('committedBookDate', () => {
  it('ignores positions newer than the committed snapshot', () => {
    expect(committedBookDate('2026-08-28', ['2026-08-31', '2026-08-28', '2026-08-27'])).toBe(
      '2026-08-28'
    );
  });

  it('returns null when the only positions are newer than the snapshot', () => {
    expect(committedBookDate('2026-08-28', ['2026-08-31'])).toBeNull();
  });

  it('returns null without a snapshot instead of falling back to latest positions', () => {
    expect(committedBookDate(null, ['2026-08-31', '2026-08-28'])).toBeNull();
    expect(committedBookDate(undefined, ['2026-08-31'])).toBeNull();
  });

  it('uses the latest on-or-before date when the snapshot date has no book', () => {
    expect(committedBookDate('2026-08-28', ['2026-08-27', '2026-08-26'])).toBe('2026-08-27');
  });
});

describe('previousBookDate', () => {
  it('picks the prior date strictly before the committed book', () => {
    expect(previousBookDate('2026-08-28', ['2026-08-31', '2026-08-28', '2026-08-27'])).toBe(
      '2026-08-27'
    );
  });
});

describe('bookedCoversCommittedSnapshot', () => {
  it('is false when the book date is newer than the snapshot', () => {
    expect(bookedCoversCommittedSnapshot('2026-08-28', '2026-08-31')).toBe(false);
  });

  it('is true only on an exact date match', () => {
    expect(bookedCoversCommittedSnapshot('2026-08-28', '2026-08-28')).toBe(true);
    expect(bookedCoversCommittedSnapshot('2026-08-28', '2026-08-27')).toBe(false);
    expect(bookedCoversCommittedSnapshot('2026-08-28', null)).toBe(false);
  });
});

describe('unpublishedBookNote', () => {
  it('is silent when no position date is newer than the snapshot', () => {
    expect(unpublishedBookNote('2026-08-28', ['2026-08-28', '2026-08-27'])).toBeNull();
  });

  it('notes when a position date is newer than the committed snapshot', () => {
    expect(unpublishedBookNote('2026-08-28', ['2026-08-31', '2026-08-28'])).toBe(
      'Last committed snapshot is 2026-08-28. Newer positions are hidden until a snapshot exists for that date.'
    );
  });

  it('is silent without a snapshot', () => {
    expect(unpublishedBookNote(null, ['2026-08-31'])).toBeNull();
  });
});

describe('assertDailySnapshotQueryOk', () => {
  it('throws on a query error', () => {
    expect(() => assertDailySnapshotQueryOk({ message: 'permission denied' })).toThrow(
      /Daily snapshot query failed/
    );
  });

  it('does not throw when the query succeeded', () => {
    expect(() => assertDailySnapshotQueryOk(null)).not.toThrow();
    expect(() => assertDailySnapshotQueryOk(undefined)).not.toThrow();
  });
});
