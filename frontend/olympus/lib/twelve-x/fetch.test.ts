import { describe, expect, it } from 'vitest';
import {
  assembleIntelligenceWhy,
  boardColumn,
  normalizeKeyThemes,
  sortTodayBriefs,
  filterEventsToDay,
} from './fetch';
import type {
  FxBriefRow,
  FxConfluenceSnapshotRow,
  FxConsensusSnapshotRow,
  FxEconomicCalendarRow,
  FxLedgerRow,
} from './types';

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

const confluence = (over: Partial<FxConfluenceSnapshotRow>): FxConfluenceSnapshotRow => ({
  run_date: '2026-06-24', rank: 1, title: 'USD long', currency: 'USD',
  direction: 'long', score: 0.8,
  components: {
    consensus_strength: 0.84, event_alignment: 0.8, recency: 1.0, breadth: 0.85,
    n_brokers: 17, days_to_catalyst: 0, timeframe: '1-3M',
  },
  brief_keys: [], as_of: '2026-06-24T00:00:00Z', ...over,
});

const consensus = (over: Partial<FxConsensusSnapshotRow>): FxConsensusSnapshotRow => ({
  run_date: '2026-06-24', currency: 'USD', timeframe: 'medium', horizon_weeks: null,
  weighted: true, score: 1.1, confidence: 0.7, agreement: 0.66, tilt: 0.5,
  n_eff: 12, n_brokers: 17, n_views: 21,
  bullish_pct: 60, bearish_pct: 10, neutral_pct: 20, watch_pct: 10,
  as_of: '2026-06-24T00:00:00Z', ...over,
});

const ledger = (over: Partial<FxLedgerRow>): FxLedgerRow => ({
  run_date: '2026-06-24', source_file: 's.pdf', view_index: 0, broker_name: 'Atlas Macro',
  currency: 'USD', direction: 'bullish', conviction: 'high', report_date: '2026-06-24',
  w_time: 1.0, w_event: 1.0, w_review: 0.9, relevance: 0.92, classification: 'active',
  reason: 'US rate resilience keeps the dollar bid.', as_of: '2026-06-24T00:00:00Z', ...over,
});

/**
 * `assembleIntelligenceWhy` is the PURE Tier-1/2/3 join behind the Intelligence
 * "why" panel: per confluence idea it pulls the score legs from `components`,
 * the canonical (medium/weighted) consensus decomposition, and the supporting
 * ledger desks for that currency. It must NOT surface w_time/w_event.
 */
describe('assembleIntelligenceWhy', () => {
  it('joins confluence + consensus + ledger desks per currency', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD', rank: 1 })],
      [consensus({ currency: 'USD' })],
      [ledger({ currency: 'USD', broker_name: 'Atlas Macro' }), ledger({ currency: 'EUR', broker_name: 'Other' })],
      '2026-06-24'
    );
    expect(out.runDate).toBe('2026-06-24');
    expect(out.items).toHaveLength(1);
    const item = out.items[0];
    expect(item.currency).toBe('USD');
    expect(item.rank).toBe(1);
    expect(item.score).toBeCloseTo(0.8);
    // Tier 1 legs extracted from components jsonb.
    expect(item.components.consensus_strength).toBeCloseTo(0.84);
    expect(item.components.event_alignment).toBeCloseTo(0.8);
    expect(item.components.recency).toBeCloseTo(1.0);
    expect(item.components.breadth).toBeCloseTo(0.85);
    expect(item.components.n_brokers).toBe(17);
    expect(item.components.timeframe).toBe('1-3M');
    // Tier 2 consensus decomposition.
    expect(item.consensus?.score).toBeCloseTo(1.1);
    expect(item.consensus?.confidence).toBeCloseTo(0.7);
    expect(item.consensus?.bullish_pct).toBe(60);
    // Tier 3 desks — only the USD desk, NOT the EUR one.
    expect(item.desks).toHaveLength(1);
    expect(item.desks[0].broker).toBe('Atlas Macro');
    expect(item.desks[0].classification).toBe('active');
    expect(item.desks[0].relevance).toBeCloseTo(0.92);
    expect(item.desks[0].reason).toBe('US rate resilience keeps the dollar bid.');
  });

  it('does NOT carry w_time / w_event onto assembled desks', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD' })],
      [consensus({ currency: 'USD' })],
      [ledger({ currency: 'USD' })],
      '2026-06-24'
    );
    const desk = out.items[0].desks[0] as unknown as Record<string, unknown>;
    expect('w_time' in desk).toBe(false);
    expect('w_event' in desk).toBe(false);
  });

  it('matches the BASE currency of a pair (EUR/USD → EUR consensus & desks)', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'EUR/USD', rank: 2 })],
      [consensus({ currency: 'EUR', score: -0.4 })],
      [ledger({ currency: 'EUR', broker_name: 'Harbour' })],
      '2026-06-24'
    );
    expect(out.items[0].consensus?.score).toBeCloseTo(-0.4);
    expect(out.items[0].desks).toHaveLength(1);
    expect(out.items[0].desks[0].broker).toBe('Harbour');
  });

  it('orders desks by relevance descending', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'USD' })],
      [consensus({ currency: 'USD' })],
      [
        ledger({ currency: 'USD', broker_name: 'Low', relevance: 0.4 }),
        ledger({ currency: 'USD', broker_name: 'High', relevance: 0.92 }),
        ledger({ currency: 'USD', broker_name: 'Mid', relevance: 0.7 }),
      ],
      '2026-06-24'
    );
    expect(out.items[0].desks.map((d) => d.broker)).toEqual(['High', 'Mid', 'Low']);
  });

  it('yields a null consensus when no matching consensus row exists', () => {
    const out = assembleIntelligenceWhy(
      [confluence({ currency: 'JPY' })],
      [consensus({ currency: 'USD' })],
      [],
      '2026-06-24'
    );
    expect(out.items[0].consensus).toBeNull();
    expect(out.items[0].desks).toEqual([]);
  });

  it('preserves confluence rank order', () => {
    const out = assembleIntelligenceWhy(
      [
        confluence({ currency: 'JPY', rank: 2 }),
        confluence({ currency: 'USD', rank: 1 }),
      ],
      [],
      [],
      '2026-06-24'
    );
    expect(out.items.map((i) => i.rank)).toEqual([1, 2]);
  });
});
