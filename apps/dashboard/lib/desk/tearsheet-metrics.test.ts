import { describe, expect, it } from 'vitest';
import { TEARSHEET_MIN_OVERLAP_DAYS, formatOverlapGatedMetric } from './tearsheet-metrics';

describe('formatOverlapGatedMetric', () => {
  it('renders an em dash under the overlap floor and when the metric is null', () => {
    expect(formatOverlapGatedMetric(1.2, TEARSHEET_MIN_OVERLAP_DAYS - 1)).toBe('—');
    expect(formatOverlapGatedMetric(null, TEARSHEET_MIN_OVERLAP_DAYS)).toBe('—');
    expect(formatOverlapGatedMetric(1.2, TEARSHEET_MIN_OVERLAP_DAYS)).toBe('+1.2');
  });
});
