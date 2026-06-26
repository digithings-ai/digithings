import { describe, it, expect } from 'vitest';
import { buildPipelineDayData, fanoutIdForKey } from './pipeline-graph-data';

describe('buildPipelineDayData', () => {
  it('counts fan-outs by document_key prefix', () => {
    const docs = [
      { document_key: 'alt-credit' }, { document_key: 'alt-flows' },
      { document_key: 'sector-tech' }, { document_key: 'sector-scorecard' },
      { document_key: 'analyst/SPY' }, { document_key: 'deliberation/SPY' },
      { document_key: 'digest' },
    ];
    const d = buildPipelineDayData(docs);
    expect(d.fanoutCounts['alt-data']).toBe(2);
    expect(d.fanoutCounts['sectors']).toBe(1); // scorecard excluded
    expect(d.fanoutCounts['analysts']).toBe(1);
    expect(d.presentKeys.has('digest')).toBe(true);
  });

  it('counts asset-classes by exact-set membership (not a prefix)', () => {
    const docs = [
      { document_key: 'bonds' }, { document_key: 'commodities' },
      { document_key: 'crypto' }, { document_key: 'equity' },
      { document_key: 'forex' }, { document_key: 'international' },
      { document_key: 'macro' }, // NOT an asset class
    ];
    const d = buildPipelineDayData(docs);
    expect(d.fanoutCounts['asset-classes']).toBe(6);
    expect(d.fanoutKeys['asset-classes']).toEqual([
      'bonds', 'commodities', 'crypto', 'equity', 'forex', 'international',
    ]);
  });

  it('collects SORTED fanoutKeys for each fan-out id', () => {
    const docs = [
      { document_key: 'analyst/QQQ' }, { document_key: 'analyst/TLT' },
      { document_key: 'analyst/BITO' },
      { document_key: 'deliberation/QQQ' },
      { document_key: 'sector-technology' }, { document_key: 'sector-financials' },
      { document_key: 'sector-scorecard' }, // excluded from sectors
      { document_key: 'alt-cta-positioning' }, { document_key: 'alt-sentiment-news' },
      { document_key: 'inst-hedge-fund-intel' }, { document_key: 'inst-institutional-flows' },
    ];
    const d = buildPipelineDayData(docs);
    expect(d.fanoutKeys['analysts']).toEqual(['analyst/BITO', 'analyst/QQQ', 'analyst/TLT']);
    expect(d.fanoutKeys['deliberation']).toEqual(['deliberation/QQQ']);
    expect(d.fanoutKeys['sectors']).toEqual(['sector-financials', 'sector-technology']);
    expect(d.fanoutKeys['alt-data']).toEqual(['alt-cta-positioning', 'alt-sentiment-news']);
    expect(d.fanoutKeys['institutional']).toEqual(['inst-hedge-fund-intel', 'inst-institutional-flows']);
    // counts agree with keys length
    expect(d.fanoutCounts['analysts']).toBe(3);
    expect(d.fanoutCounts['sectors']).toBe(2);
  });

  it('produces empty arrays / undefined counts when a fan-out has no docs', () => {
    const d = buildPipelineDayData([{ document_key: 'digest' }]);
    expect(d.fanoutKeys['analysts']).toEqual([]);
    expect(d.fanoutKeys['asset-classes']).toEqual([]);
    expect(d.fanoutCounts['analysts']).toBeUndefined();
  });
});

describe('fanoutIdForKey', () => {
  it('maps a branch document_key to its owning fan-out id', () => {
    expect(fanoutIdForKey('analyst/QQQ')).toBe('analysts');
    expect(fanoutIdForKey('deliberation/TLT')).toBe('deliberation');
    expect(fanoutIdForKey('sector-technology')).toBe('sectors');
    expect(fanoutIdForKey('alt-sentiment-news')).toBe('alt-data');
    expect(fanoutIdForKey('inst-hedge-fund-intel')).toBe('institutional');
    expect(fanoutIdForKey('crypto')).toBe('asset-classes');
  });

  it('returns null for non-fan-out keys', () => {
    expect(fanoutIdForKey('digest')).toBeNull();
    expect(fanoutIdForKey('pm-direction-memo')).toBeNull();
    expect(fanoutIdForKey('sector-scorecard')).toBeNull(); // excluded from sectors
    expect(fanoutIdForKey('macro')).toBeNull(); // not an asset class
  });
});
