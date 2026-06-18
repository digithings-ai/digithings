import { describe, expect, it } from 'vitest';
import {
  DEFAULT_SNAPSHOT_STALENESS_HOURS,
  formatAge,
  isStale,
} from './snapshot-staleness';

const NOW = new Date('2026-04-27T12:00:00Z');

function hoursAgo(h: number): string {
  return new Date(NOW.getTime() - h * 60 * 60 * 1000).toISOString();
}

describe('isStale', () => {
  it('treats a 1-hour-old timestamp as fresh at the 48h threshold', () => {
    expect(isStale(hoursAgo(1), 48, NOW)).toBe(false);
  });

  it('treats a 47-hour-old timestamp as fresh at the 48h threshold', () => {
    expect(isStale(hoursAgo(47), 48, NOW)).toBe(false);
  });

  it('treats a 49-hour-old timestamp as stale at the 48h threshold', () => {
    expect(isStale(hoursAgo(49), 48, NOW)).toBe(true);
  });

  it('treats an empty string as stale (fail-loud)', () => {
    expect(isStale('', 48, NOW)).toBe(true);
  });

  it('treats an unparseable timestamp as stale (fail-loud)', () => {
    expect(isStale('not-a-date', 48, NOW)).toBe(true);
  });

  it('treats a future timestamp as fresh', () => {
    const future = new Date(NOW.getTime() + 60 * 60 * 1000).toISOString();
    expect(isStale(future, 48, NOW)).toBe(false);
  });

  it('exposes the 48h default threshold', () => {
    expect(DEFAULT_SNAPSHOT_STALENESS_HOURS).toBe(48);
  });
});

describe('formatAge', () => {
  it('formats minute-level ages', () => {
    expect(formatAge(hoursAgo(0.25), NOW)).toBe('15m ago');
  });

  it('formats hour-level ages', () => {
    expect(formatAge(hoursAgo(3), NOW)).toBe('3h ago');
  });

  it('switches to days at 48h+', () => {
    expect(formatAge(hoursAgo(72), NOW)).toBe('3d ago');
  });

  it('returns null for unparseable timestamps', () => {
    expect(formatAge('not-a-date', NOW)).toBeNull();
    expect(formatAge('', NOW)).toBeNull();
  });
});
