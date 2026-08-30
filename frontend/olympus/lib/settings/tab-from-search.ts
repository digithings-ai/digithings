/**
 * Settings tab from the query string (Stripe checkout/portal return).
 */

export type SettingsTab =
  | 'profile'
  | 'pipeline'
  | 'keys'
  | 'brokers'
  | 'notifications'
  | 'billing'
  | 'about';

const TABS: ReadonlySet<SettingsTab> = new Set([
  'profile',
  'pipeline',
  'keys',
  'brokers',
  'notifications',
  'billing',
  'about',
]);

function isSettingsTab(value: string): value is SettingsTab {
  return TABS.has(value as SettingsTab);
}

/** Open Billing after Stripe return; honor ``?tab=`` otherwise. */
export function settingsTabFromSearch(search: string): SettingsTab {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const params = new URLSearchParams(raw);
  const tab = params.get('tab');
  if (tab !== null && isSettingsTab(tab)) {
    return tab;
  }
  const checkout = params.get('checkout');
  if (checkout === 'success' || checkout === 'cancel') {
    return 'billing';
  }
  return 'profile';
}
