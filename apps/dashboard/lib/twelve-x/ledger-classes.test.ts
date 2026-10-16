import { describe, expect, it } from 'vitest';
import {
  groupLedgerByClass,
  ledgerClassLabel,
  normalizeLedgerClass,
  LEDGER_CLASS_ORDER,
} from './ledger-classes';
import type { IntelligenceWhyDesk } from './types';

function desk(broker: string, classification: string): IntelligenceWhyDesk {
  return {
    broker,
    classification,
    relevance: 0.5,
    conviction: 'medium',
    direction: 'bullish',
    reason: null,
  };
}

describe('normalizeLedgerClass / ledgerClassLabel', () => {
  it('trims and lowercases, defaulting blanks to unknown', () => {
    expect(normalizeLedgerClass('  Active ')).toBe('active');
    expect(normalizeLedgerClass('')).toBe('unknown');
    expect(normalizeLedgerClass(null)).toBe('unknown');
  });

  it('capitalizes the class key for display', () => {
    expect(ledgerClassLabel('superseded')).toBe('Superseded');
    expect(ledgerClassLabel('active')).toBe('Active');
  });
});

describe('groupLedgerByClass', () => {
  it('orders known classes canonically and trails unknowns alphabetically', () => {
    const groups = groupLedgerByClass([
      desk('B3', 'superseded'),
      desk('B1', 'active'),
      desk('B9', 'zeta'),
      desk('B2', 'confirmed'),
      desk('B8', 'archived'),
      desk('B4', 'invalidated'),
    ]);
    expect(groups.map((g) => g.classification)).toEqual([
      'active',
      'confirmed',
      'invalidated',
      'superseded',
      'archived',
      'zeta',
    ]);
    expect(LEDGER_CLASS_ORDER).toContain('superseded');
  });

  it('keeps input order within a group and does not mutate the input', () => {
    const input = [desk('B1', 'active'), desk('B2', 'active')];
    const groups = groupLedgerByClass(input);
    expect(groups).toHaveLength(1);
    expect(groups[0].desks.map((d) => d.broker)).toEqual(['B1', 'B2']);
    expect(input).toHaveLength(2);
  });

  it('returns no groups for no desks', () => {
    expect(groupLedgerByClass([])).toEqual([]);
  });
});
