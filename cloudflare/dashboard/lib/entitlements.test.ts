import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Session } from '@supabase/supabase-js';
import {
  ALL_PLAN_TIERS,
  ARTIFACT_CLASSES,
  can,
  defaultSettingsTab,
  effectivePlanTier,
  requiredTierFor,
  settingsTabFromLocationHash,
  settingsTabFromSearch,
  settingsTabsVisible,
  resolveSettingsTab,
  tierFromSession,
  type ArtifactClass,
  type PlanTier,
} from './entitlements';
import {
  canAccessProduct,
  creatorEmailsFromEnv,
  resolveClientAccess,
} from './access';

/**
 * Spec §5-T5 matrix + Brief/Desk/Studio ladder:
 *
 * | Artifact class                         | Observer | Brief | Desk | Studio |
 * | Research / theses / corpus             | ✓        | ✓     | ✓    | ✓      |
 * | Portfolio narrative                    | ✓        | ✓     | ✓    | ✓      |
 * | Digest summary conclusions (teaser)    | ✓        | ✓     | ✓    | ✓      |
 * | Portfolio glimpse (no weights/NAV)     | ✓        | ✓     | ✓    | ✓      |
 * | House weights / NAV / tearsheet / …    | —        | ✓     | ✓    | ✓      |
 * | Pipeline glass-box economics           | —        | —     | ✓    | ✓      |
 * | Paper broker status                    | —        | —     | ✓    | ✓      |
 * | Private book / overlay                 | —        | —     | —    | ✓      |
 *
 * Enterprise ≡ Studio for content entitlements.
 */
const MATRIX: Record<PlanTier, Record<ArtifactClass, boolean>> = {
  free: {
    research: true,
    narrative: true,
    digest_summary: true,
    portfolio_teaser: true,
    house_weights_nav: false,
    glassbox_economics: false,
    private_book: false,
    broker_status: false,
    overlay_profile: false,
  },
  brief: {
    research: true,
    narrative: true,
    digest_summary: true,
    portfolio_teaser: true,
    house_weights_nav: true,
    glassbox_economics: false,
    private_book: false,
    broker_status: false,
    overlay_profile: false,
  },
  desk: {
    research: true,
    narrative: true,
    digest_summary: true,
    portfolio_teaser: true,
    house_weights_nav: true,
    glassbox_economics: true,
    private_book: false,
    broker_status: true,
    overlay_profile: false,
  },
  studio: {
    research: true,
    narrative: true,
    digest_summary: true,
    portfolio_teaser: true,
    house_weights_nav: true,
    glassbox_economics: true,
    private_book: true,
    broker_status: true,
    overlay_profile: true,
  },
  enterprise: {
    research: true,
    narrative: true,
    digest_summary: true,
    portfolio_teaser: true,
    house_weights_nav: true,
    glassbox_economics: true,
    private_book: true,
    broker_status: true,
    overlay_profile: true,
  },
};

describe('entitlements §5-T5 matrix', () => {
  it.each(
    ALL_PLAN_TIERS.flatMap((tier) =>
      ARTIFACT_CLASSES.map((cls) => ({ tier, cls, allowed: MATRIX[tier][cls] })),
    ),
  )('$tier × $cls → $allowed', ({ tier, cls, allowed }) => {
    expect(can(tier, cls)).toBe(allowed);
  });

  it('covers every tier × class cell (no gaps in the table-driven suite)', () => {
    expect(ALL_PLAN_TIERS).toHaveLength(5);
    expect(ARTIFACT_CLASSES).toHaveLength(9);
    expect(ALL_PLAN_TIERS.length * ARTIFACT_CLASSES.length).toBe(45);
  });
});

describe('requiredTierFor', () => {
  it('maps classes to the minimum unlock tier', () => {
    expect(requiredTierFor('research')).toBe('free');
    expect(requiredTierFor('narrative')).toBe('free');
    expect(requiredTierFor('digest_summary')).toBe('free');
    expect(requiredTierFor('portfolio_teaser')).toBe('free');
    expect(requiredTierFor('house_weights_nav')).toBe('brief');
    expect(requiredTierFor('glassbox_economics')).toBe('desk');
    expect(requiredTierFor('private_book')).toBe('studio');
    expect(requiredTierFor('broker_status')).toBe('desk');
    expect(requiredTierFor('overlay_profile')).toBe('studio');
  });
});

describe('effectivePlanTier', () => {
  it('elevates free with a studio plan_floor (creator/ops)', () => {
    expect(effectivePlanTier('free', 'studio')).toBe('studio');
    expect(effectivePlanTier('free', 'brief')).toBe('brief');
    expect(effectivePlanTier('brief', null)).toBe('brief');
    expect(effectivePlanTier('studio', 'desk')).toBe('studio');
  });
});

function sessionWithTier(planTier: unknown, email?: string): Session {
  return {
    access_token: 'test',
    refresh_token: 'test',
    expires_in: 3600,
    token_type: 'bearer',
    user: {
      id: 'u1',
      email: email ?? 'user@example.com',
      app_metadata: { plan_tier: planTier },
      user_metadata: {},
      aud: 'authenticated',
      created_at: '2026-01-01T00:00:00Z',
    },
  } as Session;
}

describe('tierFromSession', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('returns enterprise when NEXT_PUBLIC_DASHBOARD_AUTH is off (prod pre-cutover)', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(null)).toBe('enterprise');
    expect(tier(sessionWithTier('free'))).toBe('enterprise');
  });

  it('reads app_metadata.plan_tier when auth is on', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '1');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(sessionWithTier('brief'))).toBe('brief');
    expect(tier(sessionWithTier('desk'))).toBe('desk');
    expect(tier(sessionWithTier('studio'))).toBe('studio');
    expect(tier(sessionWithTier('enterprise'))).toBe('enterprise');
    expect(tier(sessionWithTier('free'))).toBe('free');
  });

  it('falls back to free when auth is on and claim is missing or unknown', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '1');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(null)).toBe('free');
    expect(tier(sessionWithTier(undefined))).toBe('free');
    expect(tier(sessionWithTier('gold'))).toBe('free');
  });
});

describe('settingsTabsVisible', () => {
  it('omits Studio+ overlay tabs for Observer/Brief; Desk adds Brokers; Studio is full', () => {
    expect(settingsTabsVisible('free').map((t) => t.id)).toEqual([
      'notifications',
      'billing',
      'about',
    ]);
    expect(settingsTabsVisible('brief').map((t) => t.id)).toEqual([
      'notifications',
      'billing',
      'about',
    ]);
    expect(settingsTabsVisible('desk').map((t) => t.id)).toEqual([
      'brokers',
      'notifications',
      'billing',
      'about',
    ]);
    expect(settingsTabsVisible('studio').map((t) => t.id)).toEqual([
      'profile',
      'pipeline',
      'keys',
      'brokers',
      'notifications',
      'billing',
      'about',
    ]);
    expect(settingsTabsVisible('enterprise').map((t) => t.id)).toEqual(
      settingsTabsVisible('studio').map((t) => t.id),
    );
  });

  it('defaults Observer to Notifications, Studio to Profile', () => {
    expect(defaultSettingsTab('free')).toBe('notifications');
    expect(defaultSettingsTab('studio')).toBe('profile');
  });

  it('settingsTabFromLocationHash selects a visible tab and ignores gated ones', () => {
    const free = settingsTabsVisible('free').map((t) => t.id);
    const studio = settingsTabsVisible('studio').map((t) => t.id);
    expect(settingsTabFromLocationHash('#billing', free)).toBe('billing');
    expect(settingsTabFromLocationHash('billing', free)).toBe('billing');
    expect(settingsTabFromLocationHash('#profile', free)).toBeNull();
    expect(settingsTabFromLocationHash('#profile', studio)).toBe('profile');
    expect(settingsTabFromLocationHash('#nope', free)).toBeNull();
    expect(settingsTabFromLocationHash('', free)).toBeNull();
  });

  it('settingsTabFromSearch honors Stripe ?tab=billing and ?checkout=', () => {
    const free = settingsTabsVisible('free').map((t) => t.id);
    const studio = settingsTabsVisible('studio').map((t) => t.id);
    expect(settingsTabFromSearch('?tab=billing', free)).toBe('billing');
    expect(settingsTabFromSearch('tab=billing&checkout=success', free)).toBe('billing');
    expect(settingsTabFromSearch('?checkout=success', free)).toBe('billing');
    expect(settingsTabFromSearch('?checkout=cancel', free)).toBe('billing');
    expect(settingsTabFromSearch('?tab=profile', free)).toBeNull();
    expect(settingsTabFromSearch('?tab=profile', studio)).toBe('profile');
    expect(settingsTabFromSearch('', free)).toBeNull();
  });

  it('resolveSettingsTab prefers query over hash', () => {
    const free = settingsTabsVisible('free').map((t) => t.id);
    expect(resolveSettingsTab('?tab=billing', '#about', free, 'notifications')).toBe(
      'billing',
    );
    expect(resolveSettingsTab('', '#about', free, 'notifications')).toBe('about');
    expect(resolveSettingsTab('', '', free, 'notifications')).toBe('notifications');
  });
});

describe('access / creator / fx_hub', () => {
  afterEach(() => {
    vi.unstubAllEnvs();
    vi.resetModules();
  });

  it('seeds creator email and fx_hub via env defaults', () => {
    expect(creatorEmailsFromEnv('')).toContain('chris.stefan@proton.me');
    expect(canAccessProduct(['fx_hub'], 'fx_hub')).toBe(true);
  });

  it('elevates creator session to studio + fx_hub without Stripe claim', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '1');
    const session = sessionWithTier('free', 'chris.stefan@proton.me');
    const snap = resolveClientAccess({ session, rpc: null });
    expect(snap.effectivePlanTier).toBe('studio');
    expect(canAccessProduct(snap.products, 'fx_hub')).toBe(true);
  });

  it('keeps non-creator free without product grants', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '1');
    const session = sessionWithTier('free', 'stranger@example.com');
    const snap = resolveClientAccess({ session, rpc: null });
    expect(snap.effectivePlanTier).toBe('free');
    expect(canAccessProduct(snap.products, 'fx_hub')).toBe(false);
  });

  it('prefers my_access RPC payload over env', () => {
    vi.stubEnv('NEXT_PUBLIC_DASHBOARD_AUTH', '1');
    const session = sessionWithTier('free', 'client@12x.example');
    const snap = resolveClientAccess({
      session,
      rpc: {
        email: 'client@12x.example',
        workspace_plan_tier: 'free',
        plan_floor: null,
        effective_plan_tier: 'free',
        products: ['fx_hub'],
      },
    });
    expect(snap.effectivePlanTier).toBe('free');
    expect(canAccessProduct(snap.products, 'fx_hub')).toBe(true);
  });
});
