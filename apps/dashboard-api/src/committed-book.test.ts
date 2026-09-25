/**
 * Parity tests vs `committedBookDate` / `previousBookDate` in
 * `apps/dashboard/lib/dashboard-ssot.ts` (client) and CONTRACT.md §6.1:
 * the committed-book gate never substitutes the latest position date.
 */
import { describe, it, expect } from 'vitest';
import {
  committedBookDate,
  previousBookDate,
  bookedCoversCommittedSnapshot,
} from './committed-book';

describe('committedBookDate gate (client parity)', () => {
  it('picks the latest positions date on or before the snapshot', () => {
    expect(
      committedBookDate('2026-09-24', ['2026-09-22', '2026-09-24', '2026-09-25']),
    ).toBe('2026-09-24');
  });

  it('holds back newer positions instead of substituting them', () => {
    expect(committedBookDate('2026-09-24', ['2026-09-25', '2026-09-26'])).toBeNull();
  });

  it('returns null (→ not_found) when the snapshot is missing', () => {
    expect(committedBookDate(null, ['2026-09-24'])).toBeNull();
    expect(committedBookDate(undefined, ['2026-09-24'])).toBeNull();
  });

  it('returns null when no position date is committed', () => {
    expect(committedBookDate('2026-09-24', [])).toBeNull();
  });

  it('ignores empty date strings', () => {
    expect(committedBookDate('2026-09-24', ['', '2026-09-23'])).toBe('2026-09-23');
  });
});

describe('previousBookDate', () => {
  it('picks the latest date strictly before the book date', () => {
    expect(
      previousBookDate('2026-09-24', ['2026-09-22', '2026-09-24', '2026-09-25']),
    ).toBe('2026-09-22');
  });

  it('returns null without a book date', () => {
    expect(previousBookDate(null, ['2026-09-22'])).toBeNull();
  });
});

describe('bookedCoversCommittedSnapshot', () => {
  it('is true only for an exact date match', () => {
    expect(bookedCoversCommittedSnapshot('2026-09-24', '2026-09-24')).toBe(true);
    expect(bookedCoversCommittedSnapshot('2026-09-24', '2026-09-23')).toBe(false);
    expect(bookedCoversCommittedSnapshot(null, '2026-09-24')).toBe(false);
  });
});
