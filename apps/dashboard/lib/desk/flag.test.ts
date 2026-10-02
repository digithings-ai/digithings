import { describe, expect, it } from 'vitest';
import { isDeskShellEnabled } from './flag';

describe('isDeskShellEnabled', () => {
  it('stays off unless the build env is exactly 1', () => {
    expect(isDeskShellEnabled(undefined)).toBe(false);
    expect(isDeskShellEnabled('')).toBe(false);
    expect(isDeskShellEnabled('0')).toBe(false);
    expect(isDeskShellEnabled('true')).toBe(false);
    expect(isDeskShellEnabled('1')).toBe(true);
  });
});
