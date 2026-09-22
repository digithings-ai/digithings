import type { TableRow } from './database.types';
import type { InstrumentDetails } from './types';

export type InstrumentLookup = ReadonlyMap<string, TableRow<'instruments'>>;

export interface ResolvedInstrumentIdentity {
  name: string;
  category: string;
  instrument: InstrumentDetails | null;
}

export function buildInstrumentLookup(rows: TableRow<'instruments'>[]): InstrumentLookup {
  return new Map(rows.map((row) => [row.ticker.trim().toUpperCase(), row]));
}

export function resolveInstrumentIdentity(
  position: Pick<TableRow<'positions'>, 'ticker' | 'name' | 'category'>,
  lookup: InstrumentLookup
): ResolvedInstrumentIdentity {
  const row = lookup.get(position.ticker.trim().toUpperCase()) ?? null;
  if (!row) {
    return {
      name: position.name ?? position.ticker,
      category: position.category ?? 'unknown',
      instrument: null,
    };
  }
  return {
    name: row.official_name,
    category: row.category ?? position.category ?? 'unknown',
    instrument: {
      ticker: row.ticker,
      official_name: row.official_name,
      instrument_type: row.instrument_type,
      asset_class: row.asset_class,
      category: row.category,
      sector: row.sector,
      industry: row.industry,
      exchange: row.exchange,
      currency: row.currency,
      country: row.country,
      provider: row.provider,
      provider_metadata: row.provider_metadata,
      source_updated_at: row.source_updated_at,
    },
  };
}
