/**
 * #3029 — live digiquant.io cut over to `public_accounting_nav_history` before
 * migrations 072–074 landed on prod. Silent empty NAV / “momentarily unavailable”
 * hid the contract break. These guards lock fail-closed wiring across olympus +
 * digiquant-web (no browser fallback to `public_nav_history`).
 */
import { describe, expect, it } from 'vitest';
import { existsSync, readFileSync } from 'node:fs';
import { dirname, join } from 'node:path';
import { fileURLToPath } from 'node:url';

const here = dirname(fileURLToPath(import.meta.url));
const olympusRoot = join(here, '..');
const repoRoot = join(olympusRoot, '..', '..');

describe('accounting NAV fail-closed wiring (#3029)', () => {
  it('olympus tearsheet fetch throws AccountingNavContractError (not safeSelect empty)', () => {
    const src = readFileSync(join(here, 'observability-queries.ts'), 'utf8');
    expect(src).toContain('AccountingNavContractError');
    expect(src).toContain('if (navQuery.error)');
    expect(src).toMatch(/throw new AccountingNavContractError/);
  });

  it('olympus dashboard asserts accounting NAV query ok before mapping rows', () => {
    const src = readFileSync(join(here, 'queries.ts'), 'utf8');
    expect(src).toContain('assertAccountingNavQueryOk(navRes.error)');
  });

  it('digiquant-web live book uses typed contract error and surfaces it', () => {
    const hook = join(repoRoot, 'frontend/digiquant-web/lib/live/useLivePortfolio.ts');
    const panel = join(
      repoRoot,
      'frontend/digiquant-web/components/landing/OlympusPortfolioPanel.tsx'
    );
    const contract = join(
      repoRoot,
      'frontend/digiquant-web/lib/live/accounting-nav-contract.ts'
    );
    expect(existsSync(hook)).toBe(true);
    expect(existsSync(panel)).toBe(true);
    expect(existsSync(contract)).toBe(true);
    const hookSrc = readFileSync(hook, 'utf8');
    const panelSrc = readFileSync(panel, 'utf8');
    expect(hookSrc).toContain('AccountingNavContractError');
    expect(hookSrc).toContain('ACCOUNTING_NAV_VIEW');
    expect(hookSrc).toContain('navContractError');
    expect(hookSrc).not.toMatch(/from\(["']public_nav_history["']\)/);
    expect(hookSrc).toContain('computeLivePerformanceKpis');
    expect(panelSrc).not.toContain('momentarily unavailable');
    expect(panelSrc).toContain('navContractError');
    expect(panelSrc).toContain('ContractBanner');
    expect(panelSrc).toContain('PositionsTable');
  });
});
