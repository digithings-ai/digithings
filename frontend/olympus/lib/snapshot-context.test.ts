import { describe, it, expect } from 'vitest';
import { parseActionableItems, parseRiskItems } from './snapshot-context';

describe('parseActionableItems', () => {
  it('maps structured items and sorts by priority ascending (null last)', () => {
    const out = parseActionableItems([
      { label: 'Trim XLI', priority: 2, rationale: 'rolling over' },
      { label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' },
      { label: 'Bare', priority: null, rationale: null },
    ]);
    expect(out.map((a) => a.label)).toEqual(['Monitor DXY above 120.4', 'Trim XLI', 'Bare']);
    expect(out[0]).toEqual({ label: 'Monitor DXY above 120.4', priority: 1, rationale: 'near YTD highs' });
  });
  it('degrades plain-string items and drops empties', () => {
    expect(parseActionableItems(['Hold the book', '', '  '])).toEqual([
      { label: 'Hold the book', priority: null, rationale: null },
    ]);
  });
  it('returns [] for non-array input', () => {
    expect(parseActionableItems(null)).toEqual([]);
    expect(parseActionableItems({})).toEqual([]);
  });
});

describe('parseRiskItems', () => {
  it('maps trigger + horizon_hours, preserves order', () => {
    const out = parseRiskItems([
      { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizon_hours: 48 },
      { label: 'Tail B', trigger: null, horizon_hours: null },
    ]);
    expect(out).toEqual([
      { label: 'BOJ intervention', trigger: 'USD/JPY break above 162', horizonHours: 48 },
      { label: 'Tail B', trigger: null, horizonHours: null },
    ]);
  });
  it('degrades plain strings and ignores labelless objects', () => {
    expect(parseRiskItems(['liquidity gap', { trigger: 'x' }])).toEqual([
      { label: 'liquidity gap', trigger: null, horizonHours: null },
    ]);
  });
});
