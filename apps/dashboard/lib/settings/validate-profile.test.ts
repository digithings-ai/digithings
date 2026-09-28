import { describe, expect, it } from 'vitest';
import {
  HOUSE_PROFILE_KEY,
  validateAssetPreferences,
  validateExecutionPolicy,
  validateInvestmentProfile,
  validatePipelineSchedule,
} from './validate-profile';

const allDaysTrue = {
  research: true,
  deliberation: true,
  execution: true,
};

const validPipelineSchedule = {
  schema_version: 1,
  monday: allDaysTrue,
  tuesday: allDaysTrue,
  wednesday: allDaysTrue,
  thursday: allDaysTrue,
  friday: allDaysTrue,
  saturday: allDaysTrue,
  sunday: allDaysTrue,
};

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

  it('accepts a full pipeline schedule matrix', () => {
    expect(validatePipelineSchedule(validPipelineSchedule).ok).toBe(true);
  });

  it('rejects pipeline schedule missing a weekday', () => {
    const { sunday: _drop, ...partial } = validPipelineSchedule;
    const result = validatePipelineSchedule(partial);
    expect(result.ok).toBe(false);
  });

  it('accepts default execution policy and rejects calendar bypass', () => {
    expect(validateExecutionPolicy({}).ok).toBe(true);
    const bad = validateExecutionPolicy({ calendar_mode: 'always_open' });
    expect(bad.ok).toBe(false);
  });
});
