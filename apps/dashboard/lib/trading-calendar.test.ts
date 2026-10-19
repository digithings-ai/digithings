import { describe, expect, it } from 'vitest';

import { calendarDay, todayYmd, tradingSessionsSince } from './trading-calendar';

/**
 * FX research runs MON-FRI, so digest age is counted in trading sessions, not
 * calendar days. A Friday run read on a Sunday has not aged: no session was due
 * in between. The weekday skeleton mirrors
 * clients/digiquant-tui/src/pages/trading-calendar.ts; public holidays are not
 * modelled here.
 */
describe('tradingSessionsSince', () => {
  it('counts the sessions a fresh run still covers as 0 or 1', () => {
    // Thursday's run, read Thursday and Friday: still the run the session owes.
    expect(tradingSessionsSince('2026-09-17', '2026-09-17')).toBe(0);
    expect(tradingSessionsSince('2026-09-17', '2026-09-18')).toBe(1);
  });

  it('a weekend costs nothing: Friday\'s run does not age over Sat/Sun', () => {
    expect(tradingSessionsSince('2026-09-18', '2026-09-19')).toBe(0);
    expect(tradingSessionsSince('2026-09-18', '2026-09-20')).toBe(0);
    // Monday is the first session the digest should have been refreshed by.
    expect(tradingSessionsSince('2026-09-18', '2026-09-21')).toBe(1);
  });

  it('counts the measured incident window', () => {
    // Newest digest 2026-10-14 (Wed), read 2026-10-19 (Mon): Thu, Fri, Mon.
    expect(tradingSessionsSince('2026-10-14', '2026-10-19')).toBe(3);
  });

  it('crosses month and year boundaries', () => {
    expect(tradingSessionsSince('2026-09-30', '2026-10-01')).toBe(1);
    // Thu 31 Dec -> Fri 1 Jan is one session, Mon 4 Jan is two.
    expect(tradingSessionsSince('2026-12-31', '2027-01-04')).toBe(2);
  });

  it('a same-day or future run date is zero, not aged', () => {
    expect(tradingSessionsSince('2026-09-17', '2026-09-16')).toBe(0);
    expect(tradingSessionsSince('2027-01-01', '2026-09-17')).toBe(0);
  });

  it('refuses anything that is not a real calendar date', () => {
    expect(tradingSessionsSince('not-a-date', '2026-10-05')).toBeNull();
    expect(tradingSessionsSince('2026-09-17', 'later')).toBeNull();
    expect(tradingSessionsSince('2026-13-01', '2026-10-05')).toBeNull();
    expect(tradingSessionsSince('2026-02-30', '2026-10-05')).toBeNull();
    expect(tradingSessionsSince('', '2026-10-05')).toBeNull();
  });

  it('reads a timestamp as its calendar day', () => {
    expect(tradingSessionsSince('2026-09-17T08:30:00Z', '2026-09-21')).toBe(2);
  });
});

describe('calendarDay', () => {
  it('normalises a real date and drops a time suffix', () => {
    expect(calendarDay('2026-09-17')).toBe('2026-09-17');
    expect(calendarDay('2026-09-17T08:30:00Z')).toBe('2026-09-17');
  });

  it('returns null for a missing or impossible date', () => {
    expect(calendarDay(null)).toBeNull();
    expect(calendarDay(undefined)).toBeNull();
    expect(calendarDay('')).toBeNull();
    expect(calendarDay('2026-02-30')).toBeNull();
  });
});

describe('todayYmd', () => {
  it('returns a real calendar day', () => {
    expect(todayYmd()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
  });
});
