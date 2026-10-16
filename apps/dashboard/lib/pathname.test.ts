import { describe, expect, it } from 'vitest';
import { normalizePathname } from './pathname';

describe('normalizePathname', () => {
  it('strips trailing slashes and preserves root', () => {
    expect(normalizePathname('/settings/')).toBe('/settings');
    expect(normalizePathname('/')).toBe('/');
    expect(normalizePathname('')).toBe('/');
  });
});
