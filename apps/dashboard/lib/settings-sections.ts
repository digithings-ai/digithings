/**
 * Settings page IA: one scrolling page, sectioned, with a rail. Pure helpers.
 *
 * Gating still flows from `settingsTabsVisible` (lib/entitlements): a section is
 * visible when at least one of its source tabs is visible (omitted, never
 * greyed). Every legacy tab id and hash (`#brokers`, `#keys`, `#about`,
 * `#billing`, `?tab=`, `?checkout=`) resolves through SECTION_ALIASES so Stripe
 * returns, the OAuth callback, sidebar children and bookmarks keep landing.
 */
import type { SettingsTabId } from '@/lib/entitlements';

export type SettingsSectionId =
  | 'account'
  | 'pipeline'
  | 'connections'
  | 'plan'
  | 'notifications'
  | 'appearance'
  | 'system';

export type SettingsSectionDef = {
  id: SettingsSectionId;
  label: string;
  /** One line under the section heading: what lives here. */
  blurb: string;
  /** Legacy tab ids that feed this section. Empty = always visible. */
  sources: readonly SettingsTabId[];
};

export const SETTINGS_SECTIONS: readonly SettingsSectionDef[] = [
  {
    id: 'account',
    label: 'Account',
    blurb: 'Who you are signed in as, and your investment profile.',
    sources: [],
  },
  {
    id: 'pipeline',
    label: 'Pipeline',
    blurb: 'Overlay research knobs, the weekly schedule, and recent runs.',
    sources: ['pipeline'],
  },
  {
    id: 'connections',
    label: 'Connections',
    blurb: 'Brokers and model keys in one place. Secrets are never shown after save.',
    sources: ['keys', 'brokers'],
  },
  {
    id: 'plan',
    label: 'Plan & billing',
    blurb: 'Where you are on the ladder, and what the next rung unlocks.',
    sources: ['billing'],
  },
  {
    id: 'notifications',
    label: 'Notifications',
    blurb: 'Digests and alerts, and when they last went out.',
    sources: ['notifications'],
  },
  {
    id: 'appearance',
    label: 'Appearance',
    blurb: 'Device-local display preferences. Applied immediately.',
    sources: [],
  },
  {
    id: 'system',
    label: 'System',
    blurb: 'Last run, build, data source, and the remaining-hop proof.',
    sources: ['about'],
  },
];

/** Hash / ?tab= id -> section plus the in-section anchor to scroll to. */
export const SECTION_ALIASES: Readonly<
  Record<string, { section: SettingsSectionId; anchor: string; tab?: SettingsTabId }>
> = {
  account: { section: 'account', anchor: 'account' },
  profile: { section: 'account', anchor: 'profile', tab: 'profile' },
  pipeline: { section: 'pipeline', anchor: 'pipeline', tab: 'pipeline' },
  connections: { section: 'connections', anchor: 'connections' },
  brokers: { section: 'connections', anchor: 'brokers', tab: 'brokers' },
  keys: { section: 'connections', anchor: 'keys', tab: 'keys' },
  plan: { section: 'plan', anchor: 'plan' },
  billing: { section: 'plan', anchor: 'billing', tab: 'billing' },
  notifications: { section: 'notifications', anchor: 'notifications', tab: 'notifications' },
  appearance: { section: 'appearance', anchor: 'appearance' },
  system: { section: 'system', anchor: 'system' },
  about: { section: 'system', anchor: 'about', tab: 'about' },
};

export type SettingsTarget = { section: SettingsSectionId; anchor: string };

/**
 * Where the Alpaca OAuth callback sends the user after a successful connect:
 * the Brokers anchor inside Connections (resolves for every tier that can have
 * a broker, and is ignored, not an error, for tiers that cannot).
 */
export function brokersReturnHref(settingsHome: string): string {
  const base = settingsHome.split('#', 1)[0] ?? settingsHome;
  return `${base}#brokers`;
}

/** Sections the viewer may use, in rail order. */
export function visibleSections(
  visibleTabIds: readonly SettingsTabId[],
): readonly SettingsSectionDef[] {
  return SETTINGS_SECTIONS.filter(
    (s) => s.sources.length === 0 || s.sources.some((t) => visibleTabIds.includes(t)),
  );
}

export function defaultSection(visibleTabIds: readonly SettingsTabId[]): SettingsSectionId {
  return visibleSections(visibleTabIds)[0]?.id ?? 'account';
}

function resolveId(
  id: string,
  visibleTabIds: readonly SettingsTabId[],
): SettingsTarget | null {
  const alias = SECTION_ALIASES[id];
  if (!alias) return null;
  if (!visibleSections(visibleTabIds).some((s) => s.id === alias.section)) return null;
  // A legacy tab id that is itself gated (e.g. #keys on Desk) must not resolve,
  // even when a sibling tab keeps the section visible.
  if (alias.tab && !visibleTabIds.includes(alias.tab)) return null;
  return { section: alias.section, anchor: alias.anchor };
}

/**
 * Query (`?tab=`, `?checkout=`) wins over the hash; unknown or gated ids return
 * null so the page keeps its default.
 */
export function resolveSettingsTarget(
  search: string,
  hash: string,
  visibleTabIds: readonly SettingsTabId[],
): SettingsTarget | null {
  const params = new URLSearchParams(search.startsWith('?') ? search.slice(1) : search);
  const tab = params.get('tab');
  if (tab !== null) {
    const hit = resolveId(tab, visibleTabIds);
    if (hit) return hit;
  }
  const checkout = params.get('checkout');
  if (checkout === 'success' || checkout === 'cancel') {
    const hit = resolveId('billing', visibleTabIds);
    if (hit) return hit;
  }
  const raw = (hash.startsWith('#') ? hash.slice(1) : hash).trim();
  const id = raw.split(/[?&]/, 1)[0] ?? '';
  return id ? resolveId(id, visibleTabIds) : null;
}
