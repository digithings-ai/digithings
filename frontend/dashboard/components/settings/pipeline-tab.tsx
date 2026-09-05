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
import {
  validateExecutionPolicy,
  validatePipelineSchedule,
} from '@/lib/settings/validate-profile';
import {
  STAGE_LABELS,
  STAGES,
  WEEKDAY_LABELS,
  WEEKDAYS,
  defaultExecutionPolicy,
  defaultPipelineSchedule,
  marketSessionFromTip,
  parseVenuesInput,
  policyFromTip,
  scheduleFromTip,
  toggleStage,
  type ExecutionPolicyState,
  type MarketSessionContext,
  type PipelineScheduleState,
  type StageName,
  type WeekdayName,
} from '@/lib/settings/pipeline-schedule';

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
  const [schedule, setSchedule] = useState<PipelineScheduleState>(() =>
    defaultPipelineSchedule(),
  );
  const [policy, setPolicy] = useState<ExecutionPolicyState>(() =>
    defaultExecutionPolicy(),
  );
  const [venuesInput, setVenuesInput] = useState('');
  const [marketSession, setMarketSession] = useState<MarketSessionContext | null>(
    null,
  );
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
      const nextSchedule = scheduleFromTip(next.pipeline_schedule);
      const nextPolicy = policyFromTip(next.execution_policy);
      setSchedule(nextSchedule);
      setPolicy(nextPolicy);
      setVenuesInput(nextPolicy.permitted_venues.join(', '));
      setMarketSession(marketSessionFromTip(next as unknown as Record<string, unknown>));
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

  function onToggleStage(day: WeekdayName, stage: StageName) {
    setSchedule((prev) => toggleStage(prev, day, stage));
  }

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

    const nextPolicy: ExecutionPolicyState = {
      ...policy,
      calendar_mode: 'venue_calendar',
      on_closed_session: 'defer',
      permitted_venues: parseVenuesInput(venuesInput),
    };

    const scheduleResult = validatePipelineSchedule(schedule);
    if (!scheduleResult.ok) {
      setError(scheduleResult.errors[0]?.message ?? 'Invalid pipeline schedule.');
      return;
    }
    const policyResult = validateExecutionPolicy(nextPolicy);
    if (!policyResult.ok) {
      setError(policyResult.errors[0]?.message ?? 'Invalid execution policy.');
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
        pipeline_schedule: scheduleResult.value,
        execution_policy: policyResult.value,
        watchlist: parseList(watchlist).map((t) => t.toUpperCase()),
        themes: parseList(themes).map((t) => t.toLowerCase()),
        research_budget_usd: researchBudget,
        expected_version_id: lastVersionId ?? tip?.version_id ?? null,
      });
      setPolicy(nextPolicy);
      setVenuesInput(nextPolicy.permitted_venues.join(', '));
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

      <section className="space-y-2" data-testid="pipeline-schedule-grid" aria-labelledby="pipeline-schedule-heading">
        <div>
          <h3
            id="pipeline-schedule-heading"
            className="text-[10px] font-medium uppercase tracking-widest text-ink-mute"
          >
            Stage schedule
          </h3>
          <p className="mt-1 text-xs text-ink-mute">
            User scheduling intent for the one daily graph. Research and deliberation run when
            enabled; execution days still defer when the market calendar says the session is
            closed.
          </p>
        </div>
        <div className="overflow-x-auto">
          <table className="w-full min-w-[28rem] border-collapse text-sm">
            <caption className="sr-only">
              Enable research, deliberation, and execution by weekday
            </caption>
            <thead>
              <tr>
                <th scope="col" className="border border-hair px-2 py-1.5 text-left text-ink-mute">
                  Stage
                </th>
                {WEEKDAYS.map((day) => (
                  <th
                    key={day}
                    scope="col"
                    className="border border-hair px-2 py-1.5 text-center text-ink-mute"
                  >
                    {WEEKDAY_LABELS[day]}
                  </th>
                ))}
              </tr>
            </thead>
            <tbody>
              {STAGES.map((stage) => (
                <tr key={stage}>
                  <th
                    scope="row"
                    className="border border-hair px-2 py-1.5 text-left font-medium text-ink"
                  >
                    {STAGE_LABELS[stage]}
                  </th>
                  {WEEKDAYS.map((day) => {
                    const checked = schedule[day][stage];
                    const id = `pipeline-stage-${day}-${stage}`;
                    return (
                      <td key={day} className="border border-hair px-2 py-1.5 text-center">
                        <input
                          id={id}
                          type="checkbox"
                          role="switch"
                          aria-checked={checked}
                          aria-label={`${STAGE_LABELS[stage]} on ${WEEKDAY_LABELS[day]}`}
                          checked={checked}
                          onChange={() => onToggleStage(day, stage)}
                          data-testid={`pipeline-stage-${day}-${stage}`}
                          className="h-4 w-4 accent-ink"
                        />
                      </td>
                    );
                  })}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      </section>

      <section
        className="space-y-3"
        data-testid="pipeline-execution-policy"
        aria-labelledby="pipeline-execution-heading"
      >
        <div>
          <h3
            id="pipeline-execution-heading"
            className="text-[10px] font-medium uppercase tracking-widest text-ink-mute"
          >
            Execution policy
          </h3>
          <p className="mt-1 text-xs text-ink-mute">
            Schedule toggles above are intent only. The venue market calendar is authoritative
            and cannot be bypassed — a scheduled execution on a closed session defers.
          </p>
        </div>

        <div
          className="space-y-1 border border-hair bg-term-bg/40 px-3 py-2"
          data-testid="pipeline-calendar-guard"
        >
          <p className="text-sm text-ink">
            Calendar guard:{' '}
            <span className="font-mono">{policy.calendar_mode}</span>
            {' · '}
            on closed session: <span className="font-mono">{policy.on_closed_session}</span>
          </p>
          {marketSession ? (
            <div className="text-xs text-ink-soft" data-testid="pipeline-market-session">
              <p>
                Effective session:{' '}
                {marketSession.session_label ??
                  (marketSession.is_open === true
                    ? 'open'
                    : marketSession.is_open === false
                      ? 'closed'
                      : 'unknown')}
                {marketSession.venue ? ` · ${marketSession.venue}` : ''}
              </p>
              {(marketSession.next_eligible_window || marketSession.next_open_at) && (
                <p>
                  Next eligible window:{' '}
                  {marketSession.next_eligible_window ?? marketSession.next_open_at}
                </p>
              )}
            </div>
          ) : (
            <p className="text-xs text-ink-mute" data-testid="pipeline-market-session-static">
              Live session status is not in this settings response yet. Until it is, assume the
              calendar still vetoes closed sessions and early-close windows — scheduled execution
              never forces an open.
            </p>
          )}
        </div>

        <label className="flex items-center justify-between gap-3 border border-hair bg-term-bg/40 px-3 py-2">
          <span className="text-sm text-ink-soft">Respect early close</span>
          <input
            type="checkbox"
            role="switch"
            aria-checked={policy.respect_early_close}
            checked={policy.respect_early_close}
            onChange={(e) =>
              setPolicy((prev) => ({ ...prev, respect_early_close: e.target.checked }))
            }
            data-testid="pipeline-respect-early-close"
            className="h-4 w-4 accent-ink"
          />
        </label>

        <label className="block space-y-1">
          <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
            Preferred venues
          </span>
          <input
            className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
            value={venuesInput}
            onChange={(e) => setVenuesInput(e.target.value)}
            placeholder="Empty = no preference filter"
            data-testid="pipeline-permitted-venues"
            aria-describedby="pipeline-venues-help"
          />
          <p id="pipeline-venues-help" className="text-xs text-ink-mute">
            Optional venue preference list. Empty leaves routing unconstrained; the calendar still
            applies to whatever venue is chosen.
          </p>
        </label>
      </section>

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
