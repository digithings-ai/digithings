import { describe, expect, it } from 'vitest';
import {
  HOUSE_PROFILE_KEY,
  validateAssetPreferences,
  validateInvestmentProfile,
} from './validate-profile';

describe('validate-profile', () => {
  it('accepts a valid investment profile', () => {
    const result = validateInvestmentProfile({
      risk_tolerance: 'moderate',
      horizon_years: 10,
      liquidity_needs: 'medium',
      base_currency: 'USD',
      tax_jurisdiction: 'US',
      esg_preference: 'none',
      experience_level: 'intermediate',
    });
    expect(result.ok).toBe(true);
  });

  it('rejects invalid enum without network', () => {
    const result = validateInvestmentProfile({
      risk_tolerance: 'yolo',
      horizon_years: 10,
      liquidity_needs: 'medium',
      base_currency: 'USD',
      tax_jurisdiction: 'US',
      esg_preference: 'none',
      experience_level: 'intermediate',
    });
    expect(result.ok).toBe(false);
    if (!result.ok) {
      expect(result.errors[0]?.path).toContain('risk_tolerance');
    }
  });

  it('accepts empty asset preferences', () => {
    expect(validateAssetPreferences({}).ok).toBe(true);
  });

  it('reserves house key constant', () => {
    expect(HOUSE_PROFILE_KEY).toBe('house');
  });
});
