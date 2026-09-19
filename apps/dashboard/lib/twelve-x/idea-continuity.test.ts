import { describe, expect, it } from 'vitest';
import {
  continuityForBoard,
  continuityKey,
  formatBoardDate,
  formatContinuityLine,
  formatPublishAsOf,
} from './idea-continuity';

describe('continuityKey', () => {
  it('normalizes pair and direction', () => {
    expect(continuityKey(' usd/jpy ', 'Long')).toBe('USD/JPY|long');
  });
});

describe('continuityForBoard', () => {
  it('returns empty when board missing from history', () => {
    expect(continuityForBoard('2026-08-20', []).size).toBe(0);
  });

  it('marks single-board debut', () => {
    const hist = [
      { run_date: '2026-08-20', pair: 'USD/JPY', direction: 'short', as_of: '2026-08-20T10:00:00Z' },
    ];
    const meta = continuityForBoard('2026-08-20', hist).get(continuityKey('USD/JPY', 'short'));
    expect(meta).toEqual({
      firstSuggested: '2026-08-20',
      lastUpdated: '2026-08-20T10:00:00Z',
      boardsOnThread: 1,
    });
  });

  it('walks back unbroken pair+direction streak across boards', () => {
    const hist = [
      { run_date: '2026-08-18', pair: 'EUR/USD', direction: 'long', as_of: '2026-08-18T09:00:00Z' },
      { run_date: '2026-08-19', pair: 'EUR/USD', direction: 'long', as_of: '2026-08-19T09:00:00Z' },
      { run_date: '2026-08-19', pair: 'USD/JPY', direction: 'short', as_of: '2026-08-19T09:00:00Z' },
      { run_date: '2026-08-20', pair: 'EUR/USD', direction: 'long', as_of: '2026-08-20T11:30:00Z' },
    ];
    const eur = continuityForBoard('2026-08-20', hist).get(continuityKey('EUR/USD', 'long'));
    expect(eur).toEqual({
      firstSuggested: '2026-08-18',
      lastUpdated: '2026-08-20T11:30:00Z',
      boardsOnThread: 3,
    });
  });

  it('breaks streak when a board lacks the pair+direction', () => {
    const hist = [
      { run_date: '2026-08-17', pair: 'GBP/USD', direction: 'long', as_of: '2026-08-17T09:00:00Z' },
      // 18th has ideas but not GBP long
      { run_date: '2026-08-18', pair: 'USD/JPY', direction: 'short', as_of: '2026-08-18T09:00:00Z' },
      { run_date: '2026-08-19', pair: 'GBP/USD', direction: 'long', as_of: '2026-08-19T09:00:00Z' },
      { run_date: '2026-08-20', pair: 'GBP/USD', direction: 'long', as_of: '2026-08-20T09:00:00Z' },
    ];
    const gbp = continuityForBoard('2026-08-20', hist).get(continuityKey('GBP/USD', 'long'));
    expect(gbp?.firstSuggested).toBe('2026-08-19');
    expect(gbp?.boardsOnThread).toBe(2);
  });

  it('breaks streak on direction flip', () => {
    const hist = [
      { run_date: '2026-08-18', pair: 'AUD/USD', direction: 'long', as_of: '2026-08-18T09:00:00Z' },
      { run_date: '2026-08-19', pair: 'AUD/USD', direction: 'short', as_of: '2026-08-19T09:00:00Z' },
      { run_date: '2026-08-20', pair: 'AUD/USD', direction: 'short', as_of: '2026-08-20T09:00:00Z' },
    ];
    const meta = continuityForBoard('2026-08-20', hist).get(continuityKey('AUD/USD', 'short'));
    expect(meta?.firstSuggested).toBe('2026-08-19');
    expect(meta?.boardsOnThread).toBe(2);
  });
});

describe('format helpers', () => {
  it('formats board and publish times', () => {
    expect(formatBoardDate('2026-08-12')).toBe('12 Aug');
    expect(formatPublishAsOf('2026-08-19T12:37:00Z')).toBe('19 Aug 12:37 UTC');
  });

  it('formats continuity line for debut vs streak', () => {
    expect(
      formatContinuityLine({
        firstSuggested: '2026-08-20',
        lastUpdated: '2026-08-20T10:00:00Z',
        boardsOnThread: 1,
      }),
    ).toBe('Suggested 20 Aug · Updated 20 Aug 10:00 UTC');
    expect(
      formatContinuityLine({
        firstSuggested: '2026-08-18',
        lastUpdated: '2026-08-20T11:30:00Z',
        boardsOnThread: 3,
      }),
    ).toBe('First suggested 18 Aug · Updated 20 Aug 11:30 UTC');
  });
});
