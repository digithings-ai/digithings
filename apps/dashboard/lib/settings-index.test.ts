import { describe, expect, it } from 'vitest';
import { settingsTabsVisible, SETTINGS_TAB_DEFS } from '@/lib/entitlements';
import { filterSettingsIndex, SETTINGS_INDEX } from '@/lib/settings-index';
import { SECTION_ALIASES } from '@/lib/settings-sections';

const ALL = SETTINGS_TAB_DEFS.map((t) => t.id);
const tabsFor = (tier: Parameters<typeof settingsTabsVisible>[0]) =>
  settingsTabsVisible(tier).map((t) => t.id);

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
    const observer = tabsFor('free');
    expect(filterSettingsIndex('alpaca', observer)).toEqual([]);
    expect(filterSettingsIndex('alpaca', ALL).length).toBeGreaterThan(0);
  });

  it('omits gated anchors inside a visible section', () => {
    // Desk sees Connections (brokers) and Account, but not model keys or the profile.
    const desk = tabsFor('desk');
    expect(desk).toContain('brokers');
    expect(desk).not.toContain('keys');
    expect(filterSettingsIndex('openai', desk)).toEqual([]);
    expect(filterSettingsIndex('risk tolerance', desk)).toEqual([]);
    expect(filterSettingsIndex('alpaca', desk).map((e) => e.anchor)).toEqual(['brokers']);
    expect(filterSettingsIndex('openai', ALL).map((e) => e.anchor)).toEqual(['keys']);
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
