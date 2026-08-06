import { describe, expect, it } from 'vitest';
import type { TableRow } from './database.types';
import { buildInstrumentLookup, resolveInstrumentIdentity } from './instrument-metadata';

function instrument(over: Partial<TableRow<'instruments'>> = {}): TableRow<'instruments'> {
  return {
    ticker: 'XLE',
    official_name: 'Energy Select Sector SPDR Fund',
    instrument_type: 'ETF',
    asset_class: 'EQUITY',
    category: 'sector-energy',
    sector: 'Energy',
    industry: 'Asset Management',
    exchange: 'NYSEArca',
    currency: 'USD',
    country: 'United States',
    provider: 'yahoo',
    provider_metadata: { market: 'us_market' },
    source_updated_at: '2026-07-20T00:00:00Z',
    created_at: '2026-07-20T00:00:00Z',
    updated_at: '2026-07-20T00:00:00Z',
    ...over,
  };
}

const position = {
  ticker: 'xle',
  name: 'Legacy Energy Name',
  category: 'equity_sector',
};

describe('instrument metadata resolution', () => {
  it('prefers canonical official name, category, and metadata case-insensitively', () => {
    const identity = resolveInstrumentIdentity(position, buildInstrumentLookup([instrument()]));

    expect(identity.name).toBe('Energy Select Sector SPDR Fund');
    expect(identity.category).toBe('sector-energy');
    expect(identity.instrument?.exchange).toBe('NYSEArca');
    expect(identity.instrument?.provider).toBe('yahoo');
  });

  it('falls back only to persisted position values when migration data is unavailable', () => {
    const identity = resolveInstrumentIdentity(position, buildInstrumentLookup([]));

    expect(identity).toEqual({
      name: 'Legacy Energy Name',
      category: 'equity_sector',
      instrument: null,
    });
  });

  it('uses an explicit unknown category instead of inferring from the symbol', () => {
    const identity = resolveInstrumentIdentity(
      { ticker: 'XLE', name: null, category: null },
      buildInstrumentLookup([])
    );

    expect(identity.name).toBe('XLE');
    expect(identity.category).toBe('unknown');
  });
});
