/**
 * Canonical list of all research segment document keys.
 *
 * Every entry below corresponds to one `documents` row that should exist for
 * every baseline date and be carried forward on delta days where no update
 * was warranted. The machine-readable source of truth lives at:
 *   templates/research-manifest.json
 */

export type ResearchManifestEntry = {
  /** Stable document_key / path in the `documents` table. */
  key: string;
  /** Human-readable display name (date-independent). */
  name: string;
  /** Skill file stem that authors this document. */
  skill: string;
  /** Display category — aligns with RESEARCH_CATEGORY_ORDER. */
  category: 'Market Analysis' | 'Equities' | 'Sectors' | 'Intelligence';
  /** Triage priority from daily-delta skill (mandatory | high | standard | low). */
  priority: 'mandatory' | 'high' | 'standard' | 'low';
  /** Optional ETF ticker for sector entries. */
  etf?: string;
};

export const RESEARCH_MANIFEST: ResearchManifestEntry[] = [
  // ── Core market analysis ─────────────────────────────────────────────────
  { key: 'deltas/macro.delta.md',        name: 'Macro',            skill: 'macro',                  category: 'Market Analysis', priority: 'mandatory' },
  { key: 'deltas/us-equities.delta.md',  name: 'US Equities',      skill: 'equity',                 category: 'Market Analysis', priority: 'mandatory' },
  { key: 'deltas/bonds.delta.md',        name: 'Bonds',            skill: 'bonds',                  category: 'Market Analysis', priority: 'high'      },
  { key: 'deltas/commodities.delta.md',  name: 'Commodities',      skill: 'commodities',            category: 'Market Analysis', priority: 'high'      },
  { key: 'deltas/forex.delta.md',        name: 'Forex',            skill: 'forex',                  category: 'Market Analysis', priority: 'high'      },
  { key: 'deltas/crypto.delta.md',       name: 'Crypto',           skill: 'crypto',                 category: 'Market Analysis', priority: 'mandatory' },
  { key: 'deltas/international.delta.md',name: 'International',    skill: 'international',          category: 'Market Analysis', priority: 'standard'  },

  // ── Sectors (11 GICS) ────────────────────────────────────────────────────
  { key: 'deltas/sectors/technology.delta.md',             name: 'Technology',           skill: 'sector-technology',       category: 'Sectors', priority: 'low', etf: 'XLK' },
  { key: 'deltas/sectors/financials.delta.md',             name: 'Financials',           skill: 'sector-financials',       category: 'Sectors', priority: 'low', etf: 'XLF' },
  { key: 'deltas/sectors/healthcare.delta.md',             name: 'Health Care',          skill: 'sector-healthcare',       category: 'Sectors', priority: 'low', etf: 'XLV' },
  { key: 'deltas/sectors/energy.delta.md',                 name: 'Energy',               skill: 'sector-energy',           category: 'Sectors', priority: 'low', etf: 'XLE' },
  { key: 'deltas/sectors/industrials.delta.md',            name: 'Industrials',          skill: 'sector-industrials',      category: 'Sectors', priority: 'low', etf: 'XLI' },
  { key: 'deltas/sectors/consumer-discretionary.delta.md', name: 'Consumer Discretionary', skill: 'sector-consumer-disc', category: 'Sectors', priority: 'low', etf: 'XLY' },
  { key: 'deltas/sectors/consumer-staples.delta.md',       name: 'Consumer Staples',    skill: 'sector-consumer-staples', category: 'Sectors', priority: 'low', etf: 'XLP' },
  { key: 'deltas/sectors/communication-services.delta.md', name: 'Communication Services', skill: 'sector-comms',         category: 'Sectors', priority: 'low', etf: 'XLC' },
  { key: 'deltas/sectors/real-estate.delta.md',            name: 'Real Estate',          skill: 'sector-real-estate',      category: 'Sectors', priority: 'low', etf: 'XLRE'},
  { key: 'deltas/sectors/utilities.delta.md',              name: 'Utilities',            skill: 'sector-utilities',        category: 'Sectors', priority: 'low', etf: 'XLU' },
  { key: 'deltas/sectors/materials.delta.md',              name: 'Materials',            skill: 'sector-materials',        category: 'Sectors', priority: 'low', etf: 'XLB' },

  // ── Alternative data / Intelligence ──────────────────────────────────────
  { key: 'deltas/alt/institutional-flows.delta.md', name: 'Institutional Flows', skill: 'inst-institutional-flows', category: 'Intelligence', priority: 'standard' },
  { key: 'deltas/alt/cta-positioning.delta.md',     name: 'CTA Positioning',     skill: 'alt-cta-positioning',      category: 'Intelligence', priority: 'standard' },
  { key: 'deltas/alt/options-derivatives.delta.md', name: 'Options & Derivatives', skill: 'alt-options-derivatives', category: 'Intelligence', priority: 'standard' },
  { key: 'deltas/alt/political-signals.delta.md',   name: 'Political Signals',   skill: 'alt-politician-signals',   category: 'Intelligence', priority: 'low'      },
  { key: 'deltas/alt/hedge-fund-intel.delta.md',    name: 'Hedge Fund Intel',    skill: 'inst-hedge-fund-intel',    category: 'Intelligence', priority: 'low'      },
  { key: 'deltas/alt/sentiment.delta.md',           name: 'Sentiment',           skill: 'alt-sentiment-news',       category: 'Intelligence', priority: 'standard' },
];

/** Fast O(1) lookup of manifest entries by document_key. */
export const MANIFEST_BY_KEY = new Map<string, ResearchManifestEntry>(
  RESEARCH_MANIFEST.map((e) => [e.key.toLowerCase(), e])
);
