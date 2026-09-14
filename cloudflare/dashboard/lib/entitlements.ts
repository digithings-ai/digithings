/**
 * Dashboard plan-tier → artifact-class entitlement map (execution tenancy T5).
 *
 * Spec §5-T5 matrix is the single source of truth — pin it in entitlements.test.ts.
 * Product addendum (2026-08-30): free = teaser only (`digest_summary` +
 * `portfolio_teaser`); creator/ops `plan_floor` elevates via `effectivePlanTier`
 * (see `lib/access.ts`); FX Hub is a client product grant, not a plan tier.
 *
 * Python mirror (K5 digest builder) MUST stay in sync:
 *   digiquant/src/digiquant/notify/entitlements.py
 * When either file changes the matrix, update the other in the same PR.
 */

import type { Session } from '@supabase/supabase-js';
import { isDashboardAuthEnabled } from './supabase';

/** String-match `workspaces.plan_tier` DB enum (migration 115). */
export type PlanTier = 'free' | 'brief' | 'desk' | 'studio' | 'enterprise';

/**
 * Artifact classes gated by plan tier (spec §5-T5 + Brief/Desk/Studio).
 * Observer = teaser; Brief = house weights/NAV; Desk = glass-box + paper
 * brokers; Studio = overlay / private book / BYOK.
 */
export type ArtifactClass =
  | 'research'
  | 'narrative'
  | 'digest_summary'
  | 'portfolio_teaser'
  | 'house_weights_nav'
  | 'glassbox_economics'
  | 'private_book'
  | 'broker_status'
  | 'overlay_profile';

const PLAN_TIERS: readonly PlanTier[] = [
  'free',
  'brief',
  'desk',
  'studio',
  'enterprise',
] as const;

/** Classes every authenticated Observer (free) may see — teaser, not reverse-engineer. */
const OBSERVER_CLASSES: readonly ArtifactClass[] = [
  'research',
  'narrative',
  'digest_summary',
  'portfolio_teaser',
] as const;

/** Brief adds house portfolio weights / NAV (summary outputs, no pipeline). */
const BRIEF_CLASSES: readonly ArtifactClass[] = [
  ...OBSERVER_CLASSES,
  'house_weights_nav',
] as const;

/** Desk adds house glass-box + paper broker connect. */
const DESK_CLASSES: readonly ArtifactClass[] = [
  ...BRIEF_CLASSES,
  'glassbox_economics',
  'broker_status',
] as const;

/** Studio adds private workspace overlay surfaces (own workspace only — RLS enforces). */
const STUDIO_CLASSES: readonly ArtifactClass[] = [
  ...DESK_CLASSES,
  'private_book',
  'overlay_profile',
] as const;

const ALLOWED: Record<PlanTier, ReadonlySet<ArtifactClass>> = {
  free: new Set(OBSERVER_CLASSES),
  brief: new Set(BRIEF_CLASSES),
  desk: new Set(DESK_CLASSES),
  studio: new Set(STUDIO_CLASSES),
  /** Enterprise matches Studio for content; contract seats/SLA are out of band. */
  enterprise: new Set(STUDIO_CLASSES),
};

const TIER_RANK: Record<PlanTier, number> = {
  free: 0,
  brief: 1,
  desk: 2,
  studio: 3,
  enterprise: 4,
};

export function isPlanTier(value: unknown): value is PlanTier {
  return typeof value === 'string' && (PLAN_TIERS as readonly string[]).includes(value);
}

/** Higher of two plan tiers. */
export function maxPlanTier(a: PlanTier, b: PlanTier | null | undefined): PlanTier {
  if (!b || !isPlanTier(b)) return a;
  return TIER_RANK[a] >= TIER_RANK[b] ? a : b;
}

/**
 * Whether `tier` may see `artifactClass` (UI presentation only — RLS is the hard gate).
 */
export function can(tier: PlanTier, artifactClass: ArtifactClass): boolean {
  return ALLOWED[tier].has(artifactClass);
}

/**
 * Resolve plan tier from a Supabase session.
 *
 * Flag coupling (pre-cutover): when `isDashboardAuthEnabled()` is off, return
 * `enterprise` so today's operator UI stays fully visible and T5 can merge
 * before the auth cutover.
 *
 * When auth is on: read `user.app_metadata.plan_tier`; unknown / missing → `free`
 * (fail closed for presentation). Prefer `effectivePlanTier` from `my_access`
 * when the access snapshot has loaded — JWT claim alone misses creator grants.
 */
export function tierFromSession(session: Session | null | undefined): PlanTier {
  if (!isDashboardAuthEnabled()) return 'enterprise';
  const raw = session?.user?.app_metadata?.plan_tier;
  if (isPlanTier(raw)) return raw;
  return 'free';
}

/**
 * Combine workspace/JWT tier with an ops `plan_floor` from entitlement_grants.
 */
export function effectivePlanTier(
  workspaceOrClaimTier: PlanTier,
  planFloor: PlanTier | null | undefined,
): PlanTier {
  return maxPlanTier(workspaceOrClaimTier, planFloor);
}

/** Minimum tier that unlocks a class — for locked-state upgrade copy. */
export function requiredTierFor(artifactClass: ArtifactClass): PlanTier {
  if (OBSERVER_CLASSES.includes(artifactClass)) return 'free';
  if (artifactClass === 'house_weights_nav') return 'brief';
  if (artifactClass === 'glassbox_economics' || artifactClass === 'broker_status') {
    return 'desk';
  }
  return 'studio';
}

export const ARTIFACT_CLASSES: readonly ArtifactClass[] = [
  'research',
  'narrative',
  'digest_summary',
  'portfolio_teaser',
  'house_weights_nav',
  'glassbox_economics',
  'private_book',
  'broker_status',
  'overlay_profile',
] as const;

export const ALL_PLAN_TIERS: readonly PlanTier[] = PLAN_TIERS;

/** Settings tab ids — keep in sync with `app/settings/page.tsx`. */
export type SettingsTabId =
  | 'profile'
  | 'pipeline'
  | 'keys'
  | 'brokers'
  | 'notifications'
  | 'billing'
  | 'about';

export type SettingsTabDef = {
  id: SettingsTabId;
  label: string;
  /** Artifact class required to show the tab. Null = visible on every plan. */
  requires: ArtifactClass | null;
};

/**
 * Settings IA: Studio+ overlay tabs and Desk+ Brokers are omitted (not
 * greyed) when the effective tier cannot use them. Observer/Brief never
 * see Profile, Pipeline, Keys, or Brokers. Desk sees Brokers.
 */
export const SETTINGS_TAB_DEFS: readonly SettingsTabDef[] = [
  { id: 'profile', label: 'Profile', requires: 'overlay_profile' },
  { id: 'pipeline', label: 'Pipeline', requires: 'overlay_profile' },
  { id: 'keys', label: 'Keys', requires: 'overlay_profile' },
  { id: 'brokers', label: 'Brokers', requires: 'broker_status' },
  { id: 'notifications', label: 'Notifications', requires: null },
  { id: 'billing', label: 'Billing', requires: null },
  { id: 'about', label: 'About', requires: null },
];

/** Tabs the current plan may actually use — unavailable tabs are omitted. */
export function settingsTabsVisible(tier: PlanTier): readonly SettingsTabDef[] {
  return SETTINGS_TAB_DEFS.filter(
    (tab) => tab.requires === null || can(tier, tab.requires),
  );
}

export function defaultSettingsTab(tier: PlanTier): SettingsTabId {
  return settingsTabsVisible(tier)[0]?.id ?? 'about';
}

function isSettingsTabId(value: string): value is SettingsTabId {
  return SETTINGS_TAB_DEFS.some((tab) => tab.id === value);
}

/**
 * Resolve `/settings#billing` (and sibling tab hashes) to a visible tab.
 * Unknown or gated hashes return null so the page keeps its default.
 */
export function settingsTabFromLocationHash(
  hash: string,
  visibleIds: readonly SettingsTabId[],
): SettingsTabId | null {
  const raw = (hash.startsWith('#') ? hash.slice(1) : hash).trim();
  const id = raw.split(/[?&]/, 1)[0] ?? '';
  if (!isSettingsTabId(id)) return null;
  return visibleIds.includes(id) ? id : null;
}

/**
 * Resolve Stripe checkout/portal return URLs (`?tab=billing`, `?checkout=`).
 * Query wins over hash. Gated or unknown tabs return null.
 */
export function settingsTabFromSearch(
  search: string,
  visibleIds: readonly SettingsTabId[],
): SettingsTabId | null {
  const raw = search.startsWith('?') ? search.slice(1) : search;
  const params = new URLSearchParams(raw);
  const tab = params.get('tab');
  if (tab !== null && isSettingsTabId(tab) && visibleIds.includes(tab)) {
    return tab;
  }
  const checkout = params.get('checkout');
  if (
    (checkout === 'success' || checkout === 'cancel') &&
    visibleIds.includes('billing')
  ) {
    return 'billing';
  }
  return null;
}

/** Query (`?tab=` / `?checkout=`) then hash (`#billing`), then the plan default. */
export function resolveSettingsTab(
  search: string,
  hash: string,
  visibleIds: readonly SettingsTabId[],
  fallback: SettingsTabId,
): SettingsTabId {
  return (
    settingsTabFromSearch(search, visibleIds) ??
    settingsTabFromLocationHash(hash, visibleIds) ??
    fallback
  );
}
