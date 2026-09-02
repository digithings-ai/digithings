'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  getJobs,
  getProfile,
  saveProfile,
  SettingsHttpError,
  type JobRunView,
  type ProfileTip,
  type SettingsApiOptions,
} from '@/lib/settings-api';

export type PipelineTabProps = {
  api: SettingsApiOptions | null;
  lastVersionId: string | null;
  onVersionSaved?: (versionId: string) => void;
  saveFn?: typeof saveProfile;
  getFn?: typeof getProfile;
  jobsFn?: typeof getJobs;
};

function listFromTip(values: string[] | undefined): string {
  return (values ?? []).join(', ');
}

function parseList(raw: string): string[] {
  return raw
    .split(/[\s,]+/)
    .map((t) => t.trim())
    .filter(Boolean);
}

export function PipelineTab({
  api,
  lastVersionId,
  onVersionSaved,
  saveFn = saveProfile,
  getFn = getProfile,
  jobsFn = getJobs,
}: PipelineTabProps) {
  const [tip, setTip] = useState<ProfileTip | null>(null);
  const [watchlist, setWatchlist] = useState('');
  const [themes, setThemes] = useState('');
  const [budget, setBudget] = useState('');
  const [error, setError] = useState<string | null>(null);
  const [conflict, setConflict] = useState(false);
  const [saving, setSaving] = useState(false);
  const [loading, setLoading] = useState(false);
  const [savedVersion, setSavedVersion] = useState<string | null>(null);
  const [jobs, setJobs] = useState<JobRunView[]>([]);

  const applyTip = useCallback(
    (next: ProfileTip) => {
      setTip(next);
      setWatchlist(listFromTip(next.watchlist));
      setThemes(listFromTip(next.themes));
      setBudget(
        typeof next.research_budget_usd === 'number'
          ? String(next.research_budget_usd)
          : '',
      );
      if (typeof next.version_id === 'string' && next.version_id) {
        onVersionSaved?.(next.version_id);
      }
    },
    [onVersionSaved],
  );

  const hydrate = useCallback(async () => {
    if (!api) return;
    setLoading(true);
    setError(null);
    try {
      applyTip(await getFn(api));
      try {
        setJobs(await jobsFn(api));
      } catch {
        setJobs([]);
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load pipeline knobs.');
    } finally {
      setLoading(false);
    }
  }, [api, getFn, jobsFn, applyTip]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- hydrate tip after mount */
    void hydrate();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hydrate]);

  async function onSave() {
    setError(null);
    setConflict(false);
    setSavedVersion(null);

    let researchBudget: number | null = null;
    if (budget.trim()) {
      const n = Number(budget);
      if (!Number.isFinite(n) || n < 0) {
        setError('Research budget must be a number ≥ 0.');
        return;
      }
      researchBudget = n;
    }

    if (!api) {
      setError('Sign in to save overlay pipeline settings.');
      return;
    }

    const profileKey =
      tip?.profile_key && tip.profile_key.trim() ? tip.profile_key.trim() : 'workspace';
    const label =
      tip?.label && tip.label.trim() ? tip.label.trim() : 'Workspace overlay';

    setSaving(true);
    try {
      const result = await saveFn(api, {
        profile_key: profileKey,
        label,
        investment: tip?.investment ?? null,
        assets: tip?.assets ?? null,
        watchlist: parseList(watchlist).map((t) => t.toUpperCase()),
        themes: parseList(themes).map((t) => t.toLowerCase()),
        research_budget_usd: researchBudget,
        expected_version_id: lastVersionId ?? tip?.version_id ?? null,
      });
      setSavedVersion(result.version_id);
      onVersionSaved?.(result.version_id);
    } catch (err) {
      if (err instanceof SettingsHttpError && err.status === 409) {
        setConflict(true);
      } else if (err instanceof SettingsHttpError) {
        setError(err.message);
      } else {
        setError('Unable to save pipeline settings.');
      }
    } finally {
      setSaving(false);
    }
  }

  return (
    <div className="space-y-5" data-testid="settings-pipeline-tab">
      <div>
        <h2 className="font-display text-xl text-ink tracking-tight">Pipeline</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Overlay research knobs for your workspace run. The digithings house pipeline stays
          always-on and immutable.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-ink-soft" data-testid="pipeline-loading">
          Loading overlay knobs…
        </p>
      ) : null}

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Watchlist tickers
        </span>
        <input
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          value={watchlist}
          onChange={(e) => setWatchlist(e.target.value)}
          placeholder="AAPL, MSFT"
          data-testid="pipeline-watchlist"
        />
      </label>

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Themes
        </span>
        <input
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
          value={themes}
          onChange={(e) => setThemes(e.target.value)}
          placeholder="ai, energy"
          data-testid="pipeline-themes"
        />
      </label>

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Research budget (USD)
        </span>
        <input
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          value={budget}
          onChange={(e) => setBudget(e.target.value)}
          placeholder="Leave blank for none"
          inputMode="decimal"
          data-testid="pipeline-budget"
        />
        <p className="text-xs text-ink-mute">
          Hard stop for overlay LLM spend (BYOK). House budget never pays for overlay research.
        </p>
      </label>

      <button
        type="button"
        disabled={saving}
        onClick={() => void onSave()}
        className="border border-ink bg-ink px-3 py-1.5 text-sm font-medium text-bg disabled:opacity-50"
        data-testid="pipeline-save"
      >
        {saving ? 'Saving…' : 'Save pipeline knobs'}
      </button>

      {conflict ? (
        <p className="text-sm text-warn" role="alert" data-testid="pipeline-conflict">
          Profile changed elsewhere — reload and try again.
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-down" role="alert" data-testid="pipeline-error">
          {error}
        </p>
      ) : null}
      {savedVersion ? (
        <p className="text-sm text-ink-mute" data-testid="pipeline-saved">
          Saved overlay version {savedVersion}
        </p>
      ) : null}

      <div className="space-y-2" data-testid="pipeline-runs">
        <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Overlay runs
        </p>
        <p className="text-xs text-ink-mute">
          Scheduled overlay jobs for this workspace. Skip reasons such as
          <span className="font-mono"> no_credentials</span> mean the Keys tab still needs a
          sealed BYOK row. <span className="font-mono">succeeded</span> is the remaining-hop
          proof; persist-off finishes <span className="font-mono">persist_disabled</span>.
        </p>
        {jobs.length === 0 ? (
          <p className="text-sm text-ink-mute">No overlay runs yet.</p>
        ) : (
          <ul className="divide-y divide-hair border border-hair">
            {jobs.map((job) => (
              <li
                key={job.id}
                className="px-3 py-2 text-sm"
                data-testid="pipeline-run-row"
              >
                <p className="font-mono text-ink">
                  {job.status}
                  {job.error ? ` · ${job.error}` : ''}
                </p>
                <p className="text-xs text-ink-mute">
                  {job.job_type}
                  {job.finished_at ? ` · ${job.finished_at}` : ''}
                </p>
              </li>
            ))}
          </ul>
        )}
      </div>
    </div>
  );
}
