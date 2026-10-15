/**
 * DIG-2697: no mock may be mistakable for real data.
 *
 * The worker serves `./stubs` doubles whenever `hasSupabaseEnv(env)` is false
 * (no SUPABASE_URL / SUPABASE_SERVICE_ROLE_KEY). Those doubles are the same
 * book shapes the real Supabase source returns, so before this slice every
 * stub-served success claimed a REAL provenance source string
 * (`public_accounting_nav_history`, ...). A dashboard (or any consumer) had
 * no way to tell fabricated NAV rows from committed accounting rows — a
 * missing/rotated secret degraded silently into plausible fake numbers.
 *
 * CONTRACT.md section 1 requires the opposite: "Badges always describe the
 * source of the displayed numbers." These tests pin that requirement on the
 * stub branch.
 */

import { describe, expect, it } from 'vitest';
import app, { type Env } from './index';
import { STUB_NULL_AS_OF } from './stubs';

const NO_ENV: Env = {};
const get = (path: string) => new Request(`https://x${path}`);

interface ProvenanceShape {
  provenance?: { source?: string; [k: string]: unknown };
}

async function provenanceOf(path: string): Promise<Record<string, unknown> | undefined> {
  const res = await app.fetch(get(path), NO_ENV);
  expect(res.status).toBe(200);
  const body = (await res.json()) as ProvenanceShape;
  return body.provenance;
}

/** Every book-backed route the stub branch can serve a success for. */
const STUB_SERVED_ROUTES = [
  '/portfolio',
  '/allocations',
  '/nav-series',
  '/brief',
  '/performance',
  '/kpis/live',
  '/benchmarks?tickers=SPY',
  '/ledger?ticker=AAPL',
] as const;

describe('stub branch provenance is honest', () => {
  for (const path of STUB_SERVED_ROUTES) {
    it(`GET ${path} marks its provenance as stub data`, async () => {
      const provenance = await provenanceOf(path);
      expect(provenance).toBeDefined();
      // The load-bearing assertion: a stub may never claim a real table name.
      expect(provenance?.source).not.toBe('public_accounting_nav_history');
      expect(provenance?.source).not.toBe(
        'public_accounting_nav_history+daily_snapshots+positions',
      );
      expect(String(provenance?.source)).toContain('stub');
    });
  }

  it('names the stub branch with a single stable marker', async () => {
    // A per-route free-text source would let one route drift back to a real
    // table name while the others stay honest; one constant cannot.
    const sources = await Promise.all(STUB_SERVED_ROUTES.map(provenanceOf));
    const unique = new Set(sources.map((p) => String(p?.source)));
    expect(unique.size).toBe(1);
  });

  it('keeps the CONTRACT section 1 provenance keys intact', async () => {
    // The honesty marker is an ADDITION, not a replacement: the dashboard
    // reads tip_date / contract / seam / marks and must keep working.
    const provenance = await provenanceOf('/portfolio');
    for (const key of ['source', 'tip_date', 'contract', 'seam', 'marks']) {
      expect(provenance).toHaveProperty(key);
    }
  });
});

describe('stub branch does not fake failures', () => {
  it('still reaches not_found through the null-book convention', async () => {
    const res = await app.fetch(get(`/brief?asOf=${STUB_NULL_AS_OF}`), NO_ENV);
    expect(res.status).toBe(404);
    const body = (await res.json()) as { error: { code: string } };
    expect(body.error.code).toBe('not_found');
  });
});