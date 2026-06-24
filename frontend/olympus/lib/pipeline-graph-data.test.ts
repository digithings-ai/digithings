import { describe, it, expect } from 'vitest';
import { buildPipelineDayData } from './pipeline-graph-data';

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
});
