import { describe, expect, it } from 'vitest';
import { DQ_PATHS, fmtPct, fmtPrice, pathSegments } from './registry';

describe('dq path registry', () => {
  it('maps /book to GET /allocations', () => {
    expect(DQ_PATHS.book.apiRoute).toBe('/allocations');
  });
  it('splits ui paths into segments', () => {
    expect(pathSegments('/house/portfolio/holdings')).toEqual(['house', 'portfolio', 'holdings']);
  });
  it('fails closed on missing numbers', () => {
    expect(fmtPct(null)).toBe('—');
    expect(fmtPct(NaN)).toBe('—');
    expect(fmtPct(5.0031)).toBe('5.00%');
    expect(fmtPrice(undefined)).toBe('—');
    expect(fmtPrice(22.14)).toBe('22.14');
  });
});
