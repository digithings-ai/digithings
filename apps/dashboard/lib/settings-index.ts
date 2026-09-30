/**
 * Static settings search index (client-only; works in the static export).
 * Every entry jumps to an anchor id that exists on the page.
 */
import type { SettingsSectionId } from '@/lib/settings-sections';
import { SETTINGS_SECTIONS } from '@/lib/settings-sections';

export type SettingsIndexEntry = {
  id: string;
  section: SettingsSectionId;
  /** Anchor element id to scroll to. */
  anchor: string;
  label: string;
  keywords: string;
};

export const SETTINGS_INDEX: readonly SettingsIndexEntry[] = [
  { id: 'email', section: 'account', anchor: 'account', label: 'Email and sign out', keywords: 'identity login logout account' },
  { id: 'profile', section: 'account', anchor: 'profile', label: 'Investment profile', keywords: 'risk tolerance horizon liquidity esg tax excluded tickers overlay' },
  { id: 'watchlist', section: 'pipeline', anchor: 'pipeline', label: 'Watchlist and themes', keywords: 'tickers themes research budget' },
  { id: 'schedule', section: 'pipeline', anchor: 'pipeline', label: 'Stage schedule', keywords: 'week research deliberation execution run days' },
  { id: 'runs', section: 'pipeline', anchor: 'pipeline', label: 'Recent runs', keywords: 'jobs history failed succeeded overlay' },
  { id: 'connections', section: 'connections', anchor: 'connections', label: 'Connections', keywords: 'add connect revoke status fingerprint' },
  { id: 'brokers', section: 'connections', anchor: 'brokers', label: 'Brokers', keywords: 'alpaca ibkr oauth paper api key fills' },
  { id: 'keys', section: 'connections', anchor: 'keys', label: 'Model keys', keywords: 'openai anthropic groq openrouter xai gemini byok llm provider revoke key' },
  { id: 'plan', section: 'plan', anchor: 'plan', label: 'Plan', keywords: 'tier brief desk studio upgrade ladder' },
  { id: 'billing', section: 'plan', anchor: 'billing', label: 'Billing', keywords: 'stripe checkout portal invoice monthly annual' },
  { id: 'notifications', section: 'notifications', anchor: 'notifications', label: 'Notifications', keywords: 'email digest alerts holding execution hour utc' },
  { id: 'theme', section: 'appearance', anchor: 'appearance', label: 'Theme', keywords: 'dark light auto color scheme' },
  { id: 'density', section: 'appearance', anchor: 'appearance', label: 'Density', keywords: 'compact comfortable spacing' },
  { id: 'sidebar', section: 'appearance', anchor: 'appearance', label: 'Sidebar default', keywords: 'collapse expand navigation' },
  { id: 'system', section: 'system', anchor: 'system', label: 'Status and build', keywords: 'last run version data source host about' },
  { id: 'hops', section: 'system', anchor: 'about', label: 'Remaining hops', keywords: 'proof checklist blockers digest oauth checkout' },
];

function tokens(q: string): string[] {
  return q.toLowerCase().split(/\s+/).filter(Boolean);
}

/**
 * Entries matching every query token (label, keywords or section name),
 * restricted to sections the viewer can see. Empty query returns [].
 */
export function filterSettingsIndex(
  query: string,
  visible: readonly SettingsSectionId[],
): SettingsIndexEntry[] {
  const toks = tokens(query);
  if (toks.length === 0) return [];
  const sectionLabel = new Map(SETTINGS_SECTIONS.map((s) => [s.id, s.label.toLowerCase()]));
  const scored: { entry: SettingsIndexEntry; score: number }[] = [];
  for (const entry of SETTINGS_INDEX) {
    if (!visible.includes(entry.section)) continue;
    const label = entry.label.toLowerCase();
    const hay = `${label} ${entry.keywords} ${sectionLabel.get(entry.section) ?? ''}`;
    if (!toks.every((t) => hay.includes(t))) continue;
    const score = toks.reduce((n, t) => n + (label.startsWith(t) ? 3 : label.includes(t) ? 2 : 1), 0);
    scored.push({ entry, score });
  }
  return scored.sort((a, b) => b.score - a.score).map((s) => s.entry);
}
