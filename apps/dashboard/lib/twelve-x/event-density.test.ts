import { describe, expect, it } from 'vitest';
import { densitySummary, deriveEventDensity, impactWeight } from './event-density';

// No event_datetime_utc => eventLocalDateKey falls back to the feed date, so
// these tests are timezone independent.
const ev = (event_date: string, impact: string) => ({
  event_date,
  event_datetime_utc: null,
  impact,
});

describe('impactWeight', () => {
  it('weights high > medium > low and defaults unknown to low', () => {
    expect(impactWeight('High')).toBe(3);
    expect(impactWeight('medium')).toBe(2);
    expect(impactWeight('low')).toBe(1);
    expect(impactWeight(null)).toBe(1);
  });
});

describe('deriveEventDensity', () => {
  const density = deriveEventDensity([
    ev('2026-06-22', 'high'),
    ev('2026-06-22', 'medium'),
    ev('2026-06-24', 'low'),
    ev('2026-06-25', 'high'),
  ]);

  it('weights by impact and zero-fills the gap day', () => {
    expect(density.days).toEqual([
      { date: '2026-06-22', count: 5 },
      { date: '2026-06-23', count: 0 },
      { date: '2026-06-24', count: 1 },
      { date: '2026-06-25', count: 3 },
    ]);
  });

  it('reports totals and the heaviest day', () => {
    expect(density.totalEvents).toBe(4);
    expect(density.highCount).toBe(2);
    expect(density.peak).toEqual({ date: '2026-06-22', count: 5 });
    expect(densitySummary(density)).toContain('4 events, 2 high impact');
    expect(densitySummary(density)).toContain('Heaviest day 2026-06-22');
  });

  it('is empty for no events and says so in the feed voice', () => {
    const empty = deriveEventDensity([]);
    expect(empty.days).toEqual([]);
    expect(empty.peak).toBeNull();
    expect(densitySummary(empty)).toContain('no events ingested');
  });
});
