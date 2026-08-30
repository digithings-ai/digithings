'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  getNotifications,
  patchNotifications,
  SettingsHttpError,
  type NotificationPrefs,
  type SettingsApiOptions,
} from '@/lib/settings-api';

export type NotifyTabProps = {
  api: SettingsApiOptions | null;
  getFn?: typeof getNotifications;
  patchFn?: typeof patchNotifications;
};

export function NotifyTab({
  api,
  getFn = getNotifications,
  patchFn = patchNotifications,
}: NotifyTabProps) {
  const [email, setEmail] = useState('');
  const [dailyDigest, setDailyDigest] = useState(false);
  const [holdingChange, setHoldingChange] = useState(false);
  const [executionAlerts, setExecutionAlerts] = useState(false);
  const [digestHour, setDigestHour] = useState(12);
  const [message, setMessage] = useState<string | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [busy, setBusy] = useState(false);
  const [loading, setLoading] = useState(false);

  const applyPrefs = useCallback((prefs: NotificationPrefs) => {
    setEmail(typeof prefs.email === 'string' ? prefs.email : '');
    setDailyDigest(Boolean(prefs.daily_digest));
    setHoldingChange(Boolean(prefs.holding_change_alerts));
    setExecutionAlerts(Boolean(prefs.execution_alerts));
    setDigestHour(
      typeof prefs.digest_hour_utc === 'number' && Number.isInteger(prefs.digest_hour_utc)
        ? prefs.digest_hour_utc
        : 12,
    );
  }, []);

  const hydrate = useCallback(async () => {
    if (!api) return;
    setLoading(true);
    setMessage(null);
    setNotReady(false);
    try {
      const prefs = await getFn(api);
      applyPrefs(prefs);
    } catch (err) {
      if (err instanceof SettingsHttpError && (err.status === 503 || err.code === 'NOT_READY')) {
        setNotReady(true);
        setMessage(
          'Notification preferences backend is temporarily unavailable. Showing empty form.',
        );
      } else {
        setMessage(err instanceof Error ? err.message : 'Unable to load preferences.');
      }
    } finally {
      setLoading(false);
    }
  }, [api, getFn, applyPrefs]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- hydrate prefs after mount */
    void hydrate();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hydrate]);

  async function onSave() {
    setMessage(null);
    setNotReady(false);
    if (!api) {
      setMessage('Sign in to update notification preferences.');
      return;
    }
    setBusy(true);
    try {
      const saved = await patchFn(api, {
        email,
        daily_digest: dailyDigest,
        holding_change_alerts: holdingChange,
        execution_alerts: executionAlerts,
        digest_hour_utc: digestHour,
      });
      applyPrefs(saved);
      setMessage('Preferences saved.');
    } catch (err) {
      if (err instanceof SettingsHttpError && (err.status === 503 || err.code === 'NOT_READY')) {
        setNotReady(true);
        setMessage(
          'Notification preferences backend is temporarily unavailable. Your choices were not saved.',
        );
      } else {
        setMessage(err instanceof Error ? err.message : 'Unable to save preferences.');
      }
    } finally {
      setBusy(false);
    }
  }

  return (
    <div className="space-y-5" data-testid="settings-notify-tab">
      <div>
        <h2 className="font-display text-xl text-ink tracking-tight">Notifications</h2>
        <p className="mt-1 text-sm text-ink-soft">
          Digests and execution alerts use the email and toggles you save here. Digest hour is
          UTC.
        </p>
      </div>

      {loading ? (
        <p className="text-sm text-ink-mute" data-testid="notify-loading">
          Loading preferences…
        </p>
      ) : null}

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Email
        </span>
        <input
          type="email"
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
          value={email}
          onChange={(e) => setEmail(e.target.value)}
          data-testid="notify-email"
        />
      </label>

      <Toggle
        label="Daily digest"
        checked={dailyDigest}
        onChange={setDailyDigest}
        testId="notify-digest"
      />
      <Toggle
        label="Holding-change alerts"
        checked={holdingChange}
        onChange={setHoldingChange}
        testId="notify-holding"
      />
      <Toggle
        label="Execution alerts"
        checked={executionAlerts}
        onChange={setExecutionAlerts}
        testId="notify-execution"
      />

      <label className="block space-y-1 max-w-xs">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Digest hour (UTC)
        </span>
        <input
          type="number"
          min={0}
          max={23}
          className="w-full border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
          value={digestHour}
          onChange={(e) => setDigestHour(Number(e.target.value))}
          data-testid="notify-hour"
        />
      </label>

      {message ? (
        <p
          className={`text-sm ${notReady ? 'text-warn' : 'text-ink-soft'}`}
          role="status"
          data-testid="notify-message"
        >
          {message}
        </p>
      ) : null}

      <button
        type="button"
        disabled={busy || loading}
        onClick={() => void onSave()}
        className="border border-ink bg-ink px-4 py-2 text-sm font-medium text-bg disabled:opacity-50"
        data-testid="notify-save"
      >
        {busy ? 'Saving…' : 'Save preferences'}
      </button>
    </div>
  );
}

function Toggle({
  label,
  checked,
  onChange,
  testId,
}: {
  label: string;
  checked: boolean;
  onChange: (v: boolean) => void;
  testId?: string;
}) {
  return (
    <label className="flex items-center justify-between gap-3 border border-hair bg-term-bg/40 px-3 py-2">
      <span className="text-sm text-ink-soft">{label}</span>
      <input
        type="checkbox"
        checked={checked}
        onChange={(e) => onChange(e.target.checked)}
        data-testid={testId}
      />
    </label>
  );
}
