import { afterEach, describe, expect, it, vi } from 'vitest';
import type { Session } from '@supabase/supabase-js';
import {
  ALL_PLAN_TIERS,
  ARTIFACT_CLASSES,
  can,
  effectivePlanTier,
  requiredTierFor,
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
 * Spec §5-T5 matrix + free-teaser addendum:
 *
 * | Artifact class                         | Observer (free) | Baseline | Custom |
 * | Research / theses / corpus             | ✓               | ✓        | ✓      |
 * | Portfolio narrative                    | ✓               | ✓        | ✓      |
 * | Digest summary conclusions (teaser)    | ✓               | ✓        | ✓      |
 * | Portfolio glimpse (no weights/NAV)     | ✓               | ✓        | ✓      |
 * | House weights / NAV / tearsheet / …    | —               | ✓        | ✓      |
 * | Pipeline glass-box economics           | —               | ✓        | ✓      |
 * | Private book / broker / overlay        | —               | —        | ✓      |
 *
 * Enterprise ≡ Custom for content entitlements.
 * Free has no automations / broker / portfolio connections.
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
  baseline: {
    research: true,
    narrative: true,
    digest_summary: true,
    portfolio_teaser: true,
    house_weights_nav: true,
    glassbox_economics: true,
    private_book: false,
    broker_status: false,
    overlay_profile: false,
  },
  custom: {
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
    expect(ALL_PLAN_TIERS).toHaveLength(4);
    expect(ARTIFACT_CLASSES).toHaveLength(9);
    expect(ALL_PLAN_TIERS.length * ARTIFACT_CLASSES.length).toBe(36);
  });
});

describe('requiredTierFor', () => {
  it('maps classes to the minimum unlock tier', () => {
    expect(requiredTierFor('research')).toBe('free');
    expect(requiredTierFor('narrative')).toBe('free');
    expect(requiredTierFor('digest_summary')).toBe('free');
    expect(requiredTierFor('portfolio_teaser')).toBe('free');
    expect(requiredTierFor('house_weights_nav')).toBe('baseline');
    expect(requiredTierFor('glassbox_economics')).toBe('baseline');
    expect(requiredTierFor('private_book')).toBe('custom');
    expect(requiredTierFor('broker_status')).toBe('custom');
    expect(requiredTierFor('overlay_profile')).toBe('custom');
  });
});

describe('effectivePlanTier', () => {
  it('elevates free with a custom plan_floor (creator/ops)', () => {
    expect(effectivePlanTier('free', 'custom')).toBe('custom');
    expect(effectivePlanTier('free', 'baseline')).toBe('baseline');
    expect(effectivePlanTier('baseline', null)).toBe('baseline');
    expect(effectivePlanTier('custom', 'baseline')).toBe('custom');
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

  it('returns enterprise when NEXT_PUBLIC_OLYMPUS_AUTH is off (prod pre-cutover)', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(null)).toBe('enterprise');
    expect(tier(sessionWithTier('free'))).toBe('enterprise');
  });

  it('reads app_metadata.plan_tier when auth is on', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(sessionWithTier('baseline'))).toBe('baseline');
    expect(tier(sessionWithTier('custom'))).toBe('custom');
    expect(tier(sessionWithTier('enterprise'))).toBe('enterprise');
    expect(tier(sessionWithTier('free'))).toBe('free');
  });

  it('falls back to free when auth is on and claim is missing or unknown', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
    const { tierFromSession: tier } = await import('./entitlements');
    expect(tier(null)).toBe('free');
    expect(tier(sessionWithTier(undefined))).toBe('free');
    expect(tier(sessionWithTier('gold'))).toBe('free');
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

  it('elevates creator session to custom + fx_hub without Stripe claim', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
    const session = sessionWithTier('free', 'chris.stefan@proton.me');
    const snap = resolveClientAccess({ session, rpc: null });
    expect(snap.effectivePlanTier).toBe('custom');
    expect(canAccessProduct(snap.products, 'fx_hub')).toBe(true);
  });

  it('keeps non-creator free without product grants', async () => {
    vi.resetModules();
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
    const session = sessionWithTier('free', 'stranger@example.com');
    const snap = resolveClientAccess({ session, rpc: null });
    expect(snap.effectivePlanTier).toBe('free');
    expect(canAccessProduct(snap.products, 'fx_hub')).toBe(false);
  });

  it('prefers my_access RPC payload over env', () => {
    vi.stubEnv('NEXT_PUBLIC_OLYMPUS_AUTH', '1');
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
