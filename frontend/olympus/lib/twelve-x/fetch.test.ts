import { describe, expect, it } from 'vitest';
import { normalizeKeyThemes } from './fetch';

/**
 * `key_themes` arrives from Supabase in several shapes depending on whether the
 * column is jsonb or text[] and how the row was written. `normalizeKeyThemes`
 * must collapse every shape to a clean `string[]`. These lock that contract so
 * an upstream change can't silently regress the digest's theme chips.
 */
describe('normalizeKeyThemes', () => {
  it('passes through a jsonb / text[] array of strings', () => {
    expect(normalizeKeyThemes(['USD strength', 'ECB hawkish'])).toEqual([
      'USD strength',
      'ECB hawkish',
    ]);
  });

  it('coerces non-string array members to strings', () => {
    // jsonb arrays can carry numbers/booleans; they should stringify, not crash.
    expect(normalizeKeyThemes([1, true, 'x'] as unknown as string[])).toEqual([
      '1',
      'true',
      'x',
    ]);
  });

  it('drops empty and whitespace-only array entries', () => {
    expect(normalizeKeyThemes(['a', '', '   ', 'b'])).toEqual(['a', 'b']);
  });

  it('parses a JSON-encoded array string', () => {
    expect(normalizeKeyThemes('["a", "b"]')).toEqual(['a', 'b']);
  });

  it('trims before detecting a JSON-encoded array string', () => {
    expect(normalizeKeyThemes('  ["a","b"]  ')).toEqual(['a', 'b']);
  });

  it('treats a plain (non-JSON) string as a single theme', () => {
    expect(normalizeKeyThemes('EUR finding support')).toEqual(['EUR finding support']);
  });

  it('falls back to the raw string when a "[..." value is not valid JSON', () => {
    expect(normalizeKeyThemes('[unterminated')).toEqual(['[unterminated']);
  });

  it('returns [] for an empty or whitespace-only string', () => {
    expect(normalizeKeyThemes('')).toEqual([]);
    expect(normalizeKeyThemes('   ')).toEqual([]);
  });

  it('returns [] for null', () => {
    expect(normalizeKeyThemes(null)).toEqual([]);
  });

  it('treats a non-array JSON object string as a single raw theme', () => {
    // Only `[`-prefixed strings attempt a JSON-array parse; anything else is
    // taken verbatim as one theme rather than being dropped or mis-parsed.
    expect(normalizeKeyThemes('{"a":1}')).toEqual(['{"a":1}']);
  });
});
