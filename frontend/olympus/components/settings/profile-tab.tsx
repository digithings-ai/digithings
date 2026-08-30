'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  HOUSE_PROFILE_KEY,
  validateAssetPreferences,
  validateInvestmentProfile,
} from '@/lib/settings/validate-profile';
import {
  getProfile,
  saveProfile,
  SettingsHttpError,
  type ProfileTip,
  type SettingsApiOptions,
} from '@/lib/settings-api';

export type ProfileTabProps = {
  api: SettingsApiOptions | null;
  /** Last-seen version id for optimistic concurrency. */
  lastVersionId: string | null;
  onVersionSaved?: (versionId: string) => void;
  /** Injected save for tests. */
  saveFn?: typeof saveProfile;
  /** Injected GET for tests. */
  getFn?: typeof getProfile;
};

const DEFAULT_INVESTMENT = {
  schema_version: 1,
  risk_tolerance: 'moderate',
  horizon_years: 10,
  liquidity_needs: 'medium',
  base_currency: 'USD',
  tax_jurisdiction: 'US',
  esg_preference: 'none',
  excluded_sectors: [] as string[],
  experience_level: 'intermediate',
};

function investmentFromTip(tip: ProfileTip): typeof DEFAULT_INVESTMENT {
  const inv = tip.investment;
  if (!inv || typeof inv !== 'object') return { ...DEFAULT_INVESTMENT };
  return {
    ...DEFAULT_INVESTMENT,
    ...inv,
    excluded_sectors: Array.isArray(inv.excluded_sectors)
      ? (inv.excluded_sectors as string[])
      : [],
  };
}

function excludedTickersFromTip(tip: ProfileTip): string {
  const assets = tip.assets;
  if (!assets || typeof assets !== 'object') return '';
  const tickers = assets.excluded_tickers;
  if (!Array.isArray(tickers)) return '';
  return tickers.filter((t): t is string => typeof t === 'string').join(', ');
}

export function ProfileTab({
  api,
  lastVersionId,
  onVersionSaved,
  saveFn = saveProfile,
  getFn = getProfile,
}: ProfileTabProps) {
  const [profileKey, setProfileKey] = useState('workspace');
  const [label, setLabel] = useState('Workspace overlay');
  const [investment, setInvestment] = useState({ ...DEFAULT_INVESTMENT });
  const [excludedTickers, setExcludedTickers] = useState('');
  const [pipelineWatchlist, setPipelineWatchlist] = useState<string[]>([]);
  const [pipelineThemes, setPipelineThemes] = useState<string[]>([]);
  const [pipelineBudget, setPipelineBudget] = useState<number | null>(null);
  const [fieldError, setFieldError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [savedVersion, setSavedVersion] = useState<string | null>(null);

  const applyTip = useCallback(
    (tip: ProfileTip) => {
      if (typeof tip.profile_key === 'string' && tip.profile_key.trim()) {
        setProfileKey(tip.profile_key);
      }
      if (typeof tip.label === 'string' && tip.label.trim()) {
        setLabel(tip.label);
      }
      setInvestment(investmentFromTip(tip));
      setExcludedTickers(excludedTickersFromTip(tip));
      setPipelineWatchlist(Array.isArray(tip.watchlist) ? tip.watchlist : []);
      setPipelineThemes(Array.isArray(tip.themes) ? tip.themes : []);
      setPipelineBudget(
        typeof tip.research_budget_usd === 'number' ? tip.research_budget_usd : null,
      );
      if (typeof tip.version_id === 'string' && tip.version_id) {
        onVersionSaved?.(tip.version_id);
      }
    },
    [onVersionSaved],
  );

  const hydrate = useCallback(async () => {
    if (!api) return;
    setLoading(true);
    setFieldError(null);
    try {
      const tip = await getFn(api);
      applyTip(tip);
    } catch (err) {
      if (err instanceof SettingsHttpError && (err.status === 503 || err.code === 'NOT_READY')) {
        setFieldError(
          'Profile backend is temporarily unavailable. Showing empty form.',
        );
      } else {
        setFieldError(err instanceof Error ? err.message : 'Unable to load profile.');
      }
    } finally {
      setLoading(false);
    }
  }, [api, getFn, applyTip]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- hydrate tip after mount */
    void hydrate();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hydrate]);

  async function onSave() {
    setFieldError(null);
    setConflict(false);
    setSavedVersion(null);

    if (profileKey.trim() === HOUSE_PROFILE_KEY) {
      setFieldError('The house profile key is reserved — choose another overlay key.');
      return;
    }

    const invResult = validateInvestmentProfile(investment);
    if (!invResult.ok) {
      const err = invResult.errors[0]!;
      setFieldError(`${err.path || 'investment'}: ${err.message}`);
      return;
    }

    const assetsPayload = {
      schema_version: 1,
      watchlists: {},
      custom_universe: [],
      excluded_tickers: excludedTickers
        .split(/[\s,]+/)
        .map((t) => t.trim().toUpperCase())
        .filter(Boolean),
      excluded_sectors: [],
    };
    const assetsResult = validateAssetPreferences(assetsPayload);
    if (!assetsResult.ok) {
      const err = assetsResult.errors[0]!;
      setFieldError(`${err.path || 'assets'}: ${err.message}`);
      return;
    }

    if (!api) {
      setFieldError('Sign in to save your overlay profile.');
      return;
    }

    setSaving(true);
    try {
      const result = await saveFn(api, {
        profile_key: profileKey.trim(),
        label: label.trim(),
        investment: invResult.value,
        assets: assetsResult.value,
        watchlist: pipelineWatchlist,
        themes: pipelineThemes,
        research_budget_usd: pipelineBudget,
        expected_version_id: lastVersionId,
      });
      setSavedVersion(result.version_id);
      onVersionSaved?.(result.version_id);
    } catch (err) {
      if (err instanceof SettingsHttpError && err.status === 409) {
        setConflict(true);
      } else if (err instanceof SettingsHttpError) {
        setFieldError(err.message);
      } else {
        setFieldError('Unable to save profile.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5" data-testid="settings-profile-tab">
      <div>
        <h2 className="font-display text-xl text-ink tracking-tight">Investment profile</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Posture and asset preferences become a versioned overlay pin. The digithings house
          profile stays untouched.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-ink-soft" data-testid="profile-loading">
          Loading saved overlay…
        </p>
      ) : null}

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Overlay key
        </span>
        <input
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink font-mono"
          value={profileKey}
          onChange={(e) => setProfileKey(e.target.value)}
          data-testid="profile-key-input"
        />
      </label>

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Label
        </span>
        <input
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
          value={label}
          onChange={(e) => setLabel(e.target.value)}
        />
      </label>

      <div className="grid gap-3 sm:grid-cols-2">
        <SelectField
          label="Risk tolerance"
          value={investment.risk_tolerance}
          options={['conservative', 'moderate', 'aggressive']}
          onChange={(v) => setInvestment((s) => ({ ...s, risk_tolerance: v }))}
          testId="risk-tolerance"
        />
        <label className="block space-y-1">
          <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
            Horizon (years)
          </span>
          <input
            type="number"
            min={1}
            max={50}
            className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink font-mono"
            value={investment.horizon_years}
            onChange={(e) =>
              setInvestment((s) => ({ ...s, horizon_years: Number(e.target.value) }))
            }
            data-testid="horizon-years"
          />
        </label>
        <SelectField
          label="Liquidity needs"
          value={investment.liquidity_needs}
          options={['low', 'medium', 'high']}
          onChange={(v) => setInvestment((s) => ({ ...s, liquidity_needs: v }))}
        />
        <SelectField
          label="Experience"
          value={investment.experience_level}
          options={['novice', 'intermediate', 'expert']}
          onChange={(v) => setInvestment((s) => ({ ...s, experience_level: v }))}
        />
        <SelectField
          label="ESG preference"
          value={investment.esg_preference}
          options={['none', 'tilt', 'strict']}
          onChange={(v) => setInvestment((s) => ({ ...s, esg_preference: v }))}
        />
        <SelectField
          label="Tax jurisdiction"
          value={investment.tax_jurisdiction}
          options={['US', 'EU', 'UK', 'CA', 'AU', 'OTHER']}
          onChange={(v) => setInvestment((s) => ({ ...s, tax_jurisdiction: v }))}
        />
      </div>

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Excluded tickers
        </span>
        <input
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink font-mono"
          placeholder="TSLA, GME"
          value={excludedTickers}
          onChange={(e) => setExcludedTickers(e.target.value)}
        />
      </label>

      {fieldError ? (
        <p className="text-sm text-down" data-testid="profile-field-error" role="alert">
          {fieldError}
        </p>
      ) : null}
      {conflict ? (
        <p className="text-sm text-warn" data-testid="profile-conflict" role="alert">
          Profile changed elsewhere — reload before saving again.
        </p>
      ) : null}
      {savedVersion ? (
        <p className="text-sm text-ink-soft" data-testid="profile-saved">
          Saved version <span className="font-mono text-ink-mute">{savedVersion}</span>
        </p>
      ) : null}

      <button
        type="button"
        onClick={() => void onSave()}
        disabled={saving || loading}
        className="border border-ink bg-ink px-4 py-2 text-sm font-medium text-bg hover:opacity-90 disabled:opacity-50"
        data-testid="profile-save"
      >
        {saving ? 'Saving…' : 'Save overlay'}
      </button>
    </div>
  );
}

function SelectField({
  label,
  value,
  options,
  onChange,
  testId,
}: {
  label: string;
  value: string;
  options: string[];
  onChange: (v: string) => void;
  testId?: string;
}) {
  return (
    <label className="block space-y-1">
      <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
        {label}
      </span>
      <select
        className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
        value={value}
        onChange={(e) => onChange(e.target.value)}
        data-testid={testId}
      >
        {options.map((o) => (
          <option key={o} value={o}>
            {o}
          </option>
        ))}
      </select>
    </label>
  );
}
