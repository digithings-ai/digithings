import { describe, expect, it } from 'vitest';
import { settingsTabsVisible, type PlanTier } from '@/lib/entitlements';
import {
  brokersReturnHref,
  defaultSection,
  resolveSettingsTarget,
  visibleSections,
} from '@/lib/settings-sections';

const ids = (tier: PlanTier) => settingsTabsVisible(tier).map((t) => t.id);
const sectionIds = (tier: PlanTier) => visibleSections(ids(tier)).map((s) => s.id);

describe('visibleSections gating', () => {
  it('Observer never sees pipeline or connections', () => {
    expect(sectionIds('free')).toEqual(['account', 'plan', 'notifications', 'appearance', 'system']);
    expect(sectionIds('free')).not.toContain('pipeline');
    expect(sectionIds('free')).not.toContain('connections');
  });

  it('Desk sees connections (brokers only) but not pipeline', () => {
    expect(sectionIds('desk')).toContain('connections');
    expect(sectionIds('desk')).not.toContain('pipeline');
  });

  it('Studio sees every section in rail order', () => {
    expect(sectionIds('studio')).toEqual([
      'account',
      'pipeline',
      'connections',
      'plan',
      'notifications',
      'appearance',
      'system',
    ]);
  });

  it('default is account for everyone', () => {
    expect(defaultSection(ids('free'))).toBe('account');
  });
});

describe('resolveSettingsTarget aliases', () => {
  const studio = ids('studio');

  it('#brokers and #keys resolve to connections with their own anchor', () => {
    expect(resolveSettingsTarget('', '#brokers', studio)).toEqual({
      section: 'connections',
      anchor: 'brokers',
    });
    expect(resolveSettingsTarget('', '#keys', studio)).toEqual({
      section: 'connections',
      anchor: 'keys',
    });
  });

  it('#about -> system, #billing -> plan, #profile -> account', () => {
    expect(resolveSettingsTarget('', '#about', studio)?.section).toBe('system');
    expect(resolveSettingsTarget('', '#billing', studio)?.section).toBe('plan');
    expect(resolveSettingsTarget('', '#profile', studio)?.section).toBe('account');
  });

  it('?checkout=success lands on plan, and the query beats a hash', () => {
    expect(resolveSettingsTarget('?checkout=success', '#about', studio)?.section).toBe('plan');
    expect(resolveSettingsTarget('?tab=billing', '#about', studio)?.section).toBe('plan');
  });

  it('a gated legacy id resolves to null even if a sibling keeps the section visible', () => {
    // Desk has brokers but not keys.
    expect(resolveSettingsTarget('', '#keys', ids('desk'))).toBeNull();
    expect(resolveSettingsTarget('', '#brokers', ids('desk'))?.section).toBe('connections');
  });

  it('gated and unknown ids return null', () => {
    expect(resolveSettingsTarget('', '#profile', ids('free'))).toBeNull();
    expect(resolveSettingsTarget('', '#pipeline', ids('free'))).toBeNull();
    expect(resolveSettingsTarget('', '#nope', studio)).toBeNull();
    expect(resolveSettingsTarget('', '', studio)).toBeNull();
  });
});

describe('brokersReturnHref (OAuth return)', () => {
  it('appends #brokers to the settings home, replacing any existing hash', () => {
    expect(brokersReturnHref('/dashboard/settings/')).toBe('/dashboard/settings/#brokers');
    expect(brokersReturnHref('/dashboard/settings/#profile')).toBe('/dashboard/settings/#brokers');
  });

  it('lands on the brokers anchor for a broker-capable tier', () => {
    const href = brokersReturnHref('/dashboard/settings/');
    const hash = href.slice(href.indexOf('#'));
    expect(resolveSettingsTarget('', hash, ids('desk'))).toEqual({
      section: 'connections',
      anchor: 'brokers',
    });
  });
});
