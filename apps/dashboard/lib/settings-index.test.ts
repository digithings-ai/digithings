import { describe, expect, it } from 'vitest';
import { filterSettingsIndex, SETTINGS_INDEX } from '@/lib/settings-index';
import { SETTINGS_SECTIONS, SECTION_ALIASES } from '@/lib/settings-sections';

const ALL = SETTINGS_SECTIONS.map((s) => s.id);

describe('filterSettingsIndex', () => {
  it('empty query returns nothing', () => {
    expect(filterSettingsIndex('  ', ALL)).toEqual([]);
  });

  it('"revoke key" lands on the model keys anchor', () => {
    const hits = filterSettingsIndex('revoke key', ALL);
    expect(hits[0]?.anchor).toBe('keys');
  });

  it('requires every token to match', () => {
    expect(filterSettingsIndex('theme zzzz', ALL)).toEqual([]);
    expect(filterSettingsIndex('dark theme', ALL).map((e) => e.id)).toContain('theme');
  });

  it('omits entries from sections the viewer cannot see', () => {
    const observer = ALL.filter((s) => s !== 'connections' && s !== 'pipeline');
    expect(filterSettingsIndex('alpaca', observer)).toEqual([]);
    expect(filterSettingsIndex('alpaca', ALL).length).toBeGreaterThan(0);
  });

  it('ranks a label prefix above a keyword-only hit', () => {
    const hits = filterSettingsIndex('notifications', ALL);
    expect(hits[0]?.id).toBe('notifications');
  });

  it('every entry anchor resolves through the alias table', () => {
    for (const e of SETTINGS_INDEX) {
      expect(SECTION_ALIASES[e.anchor], e.id).toBeDefined();
      expect(SECTION_ALIASES[e.anchor]?.section, e.id).toBe(e.section);
    }
  });
});
