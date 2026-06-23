import { describe, expect, it } from 'vitest';
import { boardColumn, normalizeKeyThemes, sortTodayBriefs, filterEventsToDay } from './fetch';
import type { FxBriefRow, FxEconomicCalendarRow } from './types';

/**
 * `boardColumn` must consolidate broker view currencies into the 8 G10 matrix
 * columns IDENTICALLY to the twelve-x Notion matrix (`nodes/publish.py`
 * `_board_column`), so the two surfaces never disagree. This mirrors the
 * authoritative mapping table in twelve-x `tests/test_publish_node.py`.
 */
describe('boardColumn (Notion-matrix-consistent currency consolidation)', () => {
  it('files a single G10 currency under itself', () => {
    expect(boardColumn('USD')).toBe('USD');
    expect(boardColumn('EUR')).toBe('EUR');
    expect(boardColumn('NZD')).toBe('NZD');
  });

  it('files a pair under its BASE (numerator) currency — no decomposition, no flip', () => {
    expect(boardColumn('EUR/USD')).toBe('EUR');
    expect(boardColumn('CAD/USD')).toBe('CAD');
    expect(boardColumn('GBP/JPY')).toBe('GBP');
  });

  it('keeps NOK/SEK as valid legs but never as columns', () => {
    expect(boardColumn('USD/SEK')).toBe('USD'); // Scandi quote leg is valid → base USD
    expect(boardColumn('EUR/NOK')).toBe('EUR');
    expect(boardColumn('NOK/SEK')).toBeNull(); // both legs valid, but base NOK has no column
  });

  it('drops any view with a leg outside the extended G10 set', () => {
    expect(boardColumn('USD/IDR')).toBeNull(); // exotic quote
    expect(boardColumn('EUR/TRY')).toBeNull();
    expect(boardColumn('XAU/USD')).toBeNull(); // gold, not a currency
  });

  it('drops non-currency / junk instruments', () => {
    expect(boardColumn('DXY')).toBeNull();
    expect(boardColumn('US10Y')).toBeNull();
    expect(boardColumn('GOLD')).toBeNull();
    expect(boardColumn('')).toBeNull();
  });

  it('normalizes case and surrounding whitespace', () => {
    expect(boardColumn('usd')).toBe('USD');
    expect(boardColumn('  eur/usd  ')).toBe('EUR');
  });
});

/**
 * `key_themes` arrives from Supabase in several shapes depending on whether the
 * column is jsonb or text[] and how the row was written. `normalizeKeyThemes`
 * must collapse every shape to a clean `string[]`. These lock that contract so
 * an upstream change can't silently regress the digest's theme chips.
 */
describe('normalizeKeyThemes', () => {
  it('passes through a jsonb / text[] array of strings', () => {
    expect(normalizeKeyThemes(['USD strength', 'ECB hawkish'])).toEqual([
      'USD strength',
      'ECB hawkish',
    ]);
  });

  it('coerces non-string array members to strings', () => {
    // jsonb arrays can carry numbers/booleans; they should stringify, not crash.
    expect(normalizeKeyThemes([1, true, 'x'] as unknown as string[])).toEqual([
      '1',
      'true',
      'x',
    ]);
  });

  it('drops empty and whitespace-only array entries', () => {
    expect(normalizeKeyThemes(['a', '', '   ', 'b'])).toEqual(['a', 'b']);
  });

  it('parses a JSON-encoded array string', () => {
    expect(normalizeKeyThemes('["a", "b"]')).toEqual(['a', 'b']);
  });

  it('trims before detecting a JSON-encoded array string', () => {
    expect(normalizeKeyThemes('  ["a","b"]  ')).toEqual(['a', 'b']);
  });

  it('treats a plain (non-JSON) string as a single theme', () => {
    expect(normalizeKeyThemes('EUR finding support')).toEqual(['EUR finding support']);
  });

  it('falls back to the raw string when a "[..." value is not valid JSON', () => {
    expect(normalizeKeyThemes('[unterminated')).toEqual(['[unterminated']);
  });

  it('returns [] for an empty or whitespace-only string', () => {
    expect(normalizeKeyThemes('')).toEqual([]);
    expect(normalizeKeyThemes('   ')).toEqual([]);
  });

  it('returns [] for null', () => {
    expect(normalizeKeyThemes(null)).toEqual([]);
  });

  it('treats a non-array JSON object string as a single raw theme', () => {
    // Only `[`-prefixed strings attempt a JSON-array parse; anything else is
    // taken verbatim as one theme rather than being dropped or mis-parsed.
    expect(normalizeKeyThemes('{"a":1}')).toEqual(['{"a":1}']);
  });
});

const brief = (over: Partial<FxBriefRow>): FxBriefRow => ({
  run_date: '2026-06-23', source_file: 's.pdf', source_url: null,
  document_title: null, broker_name: 'X', analyst_names: null,
  report_date: '2026-06-23', trader_relevance: 'low', central_thesis: null,
  brief_markdown: null, currency_views: [], risk_events: null,
  macro_themes: null, positioning_signals: null, ...over,
});

describe('sortTodayBriefs', () => {
  it('orders by relevance (high→low), then breadth, then newest report_date', () => {
    const lowOld = brief({ source_file: 'a', trader_relevance: 'low', report_date: '2026-06-20' });
    const highFew = brief({ source_file: 'b', trader_relevance: 'high', currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }] });
    const highMany = brief({ source_file: 'c', trader_relevance: 'high', currency_views: [{ currency: 'USD', direction: 'bullish', conviction: 'high' }, { currency: 'EUR', direction: 'bearish', conviction: 'low' }] });
    const medNew = brief({ source_file: 'd', trader_relevance: 'medium', report_date: '2026-06-23' });
    const out = sortTodayBriefs([lowOld, highFew, highMany, medNew]).map((b) => b.source_file);
    expect(out).toEqual(['c', 'b', 'd', 'a']);
  });

  it('is stable and pure (does not mutate input)', () => {
    const input = [brief({ source_file: 'a' }), brief({ source_file: 'b' })];
    const copy = [...input];
    sortTodayBriefs(input);
    expect(input).toEqual(copy);
  });
});

const ev = (over: Partial<FxEconomicCalendarRow>): FxEconomicCalendarRow => ({
  id: 1, external_id: 'e', event_date: '2026-06-23', event_time: null,
  country: 'US', event_name: 'X', category: 'c', impact: 'low',
  actual: null, forecast: null, prior: null, event_datetime_utc: null, ...over,
});

describe('filterEventsToDay', () => {
  it('keeps only events whose local date equals the target key', () => {
    const todayUtc = ev({ id: 1, event_datetime_utc: '2026-06-23T14:30:00Z', event_date: '2026-06-23' });
    const tomorrow = ev({ id: 2, event_datetime_utc: '2026-06-24T14:30:00Z', event_date: '2026-06-24' });
    const allDayToday = ev({ id: 3, event_datetime_utc: null, event_date: '2026-06-23' });
    const key = '2026-06-23';
    const out = filterEventsToDay([todayUtc, tomorrow, allDayToday], key).map((e) => e.id);
    expect(out).toContain(1);
    expect(out).toContain(3);
    expect(out).not.toContain(2);
  });
});
