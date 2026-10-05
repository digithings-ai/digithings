import { describe, expect, it } from 'vitest';
import { blockAge, blockAgeFooter, blockAgeText, SESSION_STALE, SESSION_WARN } from '@/lib/block-age';
import { calendarDay, todayYmd, tradingSessionsSince } from '@/lib/trading-calendar';

/**
 * Window-bar age, pinned at the boundaries that decide a word.
 *
 * Anchored on the 2026-09 outage window: 2026-09-17 was a Thursday, so the
 * sessions counted from it are 18, 21, 22, ... — which is what makes a Monday
 * read of Friday's run read 2 and a Sunday read read 0.
 */
const RUN = '2026-09-17'; // Thursday
const MON = '2026-09-21'; // Monday
const TUE = '2026-09-22'; // Tuesday
const SUN = '2026-09-20'; // Sunday
const OUTAGE_READ = '2026-10-05'; // Monday

describe('tradingSessionsSince', () => {
  it('counts no session for a run read on its own day', () => {
    expect(tradingSessionsSince(MON, MON)).toBe(0);
  });

  it('counts no session across a weekend, so Friday read on Sunday is not stale', () => {
    // (Friday, Sunday] contains no weekday at all.
    expect(tradingSessionsSince('2026-09-18', SUN)).toBe(0);
    expect(tradingSessionsSince('2026-09-18', '2026-09-19')).toBe(0);
  });

  it('counts weekdays only across the weekend', () => {
    expect(tradingSessionsSince(RUN, SUN)).toBe(1);
    expect(tradingSessionsSince(RUN, MON)).toBe(2);
  });

  it('counts the outage window that made the old footer useless', () => {
    expect(tradingSessionsSince(RUN, OUTAGE_READ)).toBe(12);
  });

  it('counts across a month and a year boundary', () => {
    expect(tradingSessionsSince('2026-12-31', '2027-01-01')).toBe(1);
    expect(tradingSessionsSince('2026-12-30', '2027-01-04')).toBe(3);
  });

  it('treats a run dated ahead of the clock as skew, not as age', () => {
    expect(tradingSessionsSince(OUTAGE_READ, RUN)).toBe(0);
    expect(tradingSessionsSince(MON, '2026-09-18')).toBe(0);
  });

  it('returns null when either end cannot be read', () => {
    expect(tradingSessionsSince('not-a-date', MON)).toBeNull();
    expect(tradingSessionsSince(RUN, 'not-a-date')).toBeNull();
    expect(tradingSessionsSince(RUN, '')).toBeNull();
    // A real-looking but impossible day reads as unreadable, not as 2026-03-02.
    expect(tradingSessionsSince('2026-02-30', MON)).toBeNull();
  });

  it('reads the date out of a timestamp and drops the time', () => {
    expect(tradingSessionsSince(`${RUN}T14:02:00Z`, MON)).toBe(2);
    expect(tradingSessionsSince(`${RUN} 14:02:00`, MON)).toBe(2);
    expect(calendarDay(`${RUN}T14:02:00Z`)).toBe(RUN);
    expect(calendarDay(` ${RUN} 14:02 `)).toBe(RUN);
  });

  it('refuses a window range rather than ageing it by its start', () => {
    // One block names a window `start → end`. Reading the first token would age
    // it by the start and call an in-flight window stale.
    expect(calendarDay('2026-09-14 → 2026-09-30')).toBeNull();
    expect(tradingSessionsSince('2026-09-14 → 2026-09-30', MON)).toBeNull();
  });
});

describe('calendarDay', () => {
  it('normalises or rejects', () => {
    expect(calendarDay(RUN)).toBe(RUN);
    expect(calendarDay(null)).toBeNull();
    expect(calendarDay(undefined)).toBeNull();
    expect(calendarDay('')).toBeNull();
    expect(calendarDay('2026-13-01')).toBeNull();
    expect(calendarDay('2026-02-30')).toBeNull();
  });
});

describe('todayYmd', () => {
  it('is a local calendar day, not a UTC one', () => {
    expect(todayYmd()).toMatch(/^\d{4}-\d{2}-\d{2}$/);
    expect(todayYmd()).toBe(calendarDay(todayYmd()));
  });
});

describe('blockAge bands', () => {
  it('keeps 0-1 sessions ok, 2 warn, 3+ stale', () => {
    expect(SESSION_WARN).toBe(2);
    expect(SESSION_STALE).toBe(3);
    expect(blockAge(0)).toBe('ok');
    expect(blockAge(1)).toBe('ok');
    expect(blockAge(2)).toBe('warn');
    expect(blockAge(3)).toBe('stale');
    expect(blockAge(12)).toBe('stale');
  });
});

describe('blockAgeFooter', () => {
  const text = (runDate: string | null | undefined, now: string, route = 'desk/fx') =>
    blockAgeText(blockAgeFooter({ runDate, route, now }));

  it('keeps the route when the block carries no date', () => {
    expect(text(null, MON)).toBe('desk/fx');
    expect(text(undefined, MON)).toBe('desk/fx');
    expect(text('', MON)).toBe('desk/fx');
    expect(text('   ', MON)).toBe('desk/fx');
  });

  it('passes a non-date stamp through un-aged, because blocks pass ids and ranges', () => {
    expect(text('run-42', MON)).toBe('as of run-42');
    expect(text('2026-09-14 → 2026-09-30', MON)).toBe('as of 2026-09-14 → 2026-09-30');
    expect(text('2026-02-30', MON)).toBe('as of 2026-02-30');
    // A range reads exactly as it always did — no age, no invented staleness.
    expect(blockAgeFooter({ runDate: '2026-09-14 → 2026-09-30', route: 'desk/fx', now: MON }).state).toBeNull();
  });

  it('reports no age when the clock cannot be read', () => {
    expect(text(RUN, 'not-a-date')).toBe(`as of ${RUN}`);
  });

  it('does not claim freshness for a run dated ahead of the clock', () => {
    expect(text(OUTAGE_READ, RUN)).toBe(`as of ${OUTAGE_READ}`);
    expect(blockAgeFooter({ runDate: OUTAGE_READ, route: 'desk/fx', now: RUN }).state).toBeNull();
  });

  it('says current session for a run read this session', () => {
    expect(text(MON, MON)).toBe(`as of ${MON} · current session`);
    expect(blockAgeFooter({ runDate: MON, route: 'desk/fx', now: MON }).state).toBeNull();
  });

  it('does not warn on Monday morning for Friday run', () => {
    expect(text('2026-09-18', MON)).toBe('as of 2026-09-18 · 1 trading day old');
    expect(blockAgeFooter({ runDate: '2026-09-18', route: 'desk/fx', now: MON }).state).toBeNull();
  });

  it('names the state once the run is past a session', () => {
    expect(text(RUN, MON)).toBe(`as of ${RUN} · 2 trading days old · warn`);
    expect(text(RUN, TUE)).toBe(`as of ${RUN} · 3 trading days old · stale`);
    expect(text(RUN, OUTAGE_READ)).toBe(`as of ${RUN} · 12 trading days old · stale`);
    expect(blockAgeFooter({ runDate: RUN, route: 'desk/fx', now: TUE }).state).toBe('stale');
  });

  it('normalises a timestamp stamp before ageing it', () => {
    expect(text(`${RUN}T14:02:00Z`, MON)).toBe(`as of ${RUN} · 2 trading days old · warn`);
  });

  it('renders the same characters Block renders, in every band', () => {
    // `Block` composes `{age.lead}<span>{' '}{age.state}</span>` — the space sits
    // outside the inked span, so `lead` must not also carry it. Verified here
    // against the exact composition the component uses, so the two cannot drift.
    const asBlockRenders = (f: ReturnType<typeof blockAgeFooter>) =>
      f.state === null ? f.lead : `${f.lead} ${f.state}`;

    for (const now of [MON, TUE, OUTAGE_READ]) {
      const f = blockAgeFooter({ runDate: RUN, route: 'desk/fx', now });
      expect(blockAgeText(f)).toBe(asBlockRenders(f));
      expect(blockAgeText(f)).not.toMatch(/· {2}|·\s{2}| {2}/);
    }
    // ...and with no state word there is no trailing separator left behind.
    const fresh = blockAgeFooter({ runDate: MON, route: 'desk/fx', now: MON });
    expect(blockAgeText(fresh)).toBe(`as of ${MON} · current session`);
    expect(blockAgeText(fresh)).not.toMatch(/·\s*$/);
  });

  it('never lets an aged footer read like a fresh one', () => {
    // The defect: one footer for every age, all of it mute ink.
    const fresh = text(MON, MON);
    const aged = text(RUN, OUTAGE_READ);
    expect(fresh).not.toBe(aged);
    expect(fresh).not.toMatch(/warn|stale/);
    // A named state is a word, not a colour, so it survives a mute bar.
    expect(aged).toMatch(/stale$/);
  });
});
