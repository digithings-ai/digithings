'use client';

import { useState } from 'react';
import {
  patchNotifications,
  SettingsHttpError,
  type SettingsApiOptions,
} from '@/lib/settings-api';

export type NotifyTabProps = {
  api: SettingsApiOptions | null;
  patchFn?: typeof patchNotifications;
};

export function NotifyTab({ api, patchFn = patchNotifications }: NotifyTabProps) {
  const [email, setEmail] = useState('');
  const [dailyDigest, setDailyDigest] = useState(false);
  const [holdingChange, setHoldingChange] = useState(false);
  const [executionAlerts, setExecutionAlerts] = useState(false);
  const [digestHour, setDigestHour] = useState(12);
  const [message, setMessage] = useState<string | null>(null);
  const [notReady, setNotReady] = useState(false);
  const [busy, setBusy] = useState(false);

  async function onSave() {
    setMessage(null);
    setNotReady(false);
    if (!api) {
      setMessage('Sign in to update notification preferences.');
      return;
    }
    setBusy(true);
    try {
      await patchFn(api, {
        email,
        daily_digest: dailyDigest,
        holding_change_alerts: holdingChange,
        execution_alerts: executionAlerts,
        digest_hour_utc: digestHour,
      });
      setMessage('Preferences saved.');
    } catch (err) {
      if (err instanceof SettingsHttpError && (err.status === 503 || err.code === 'NOT_READY')) {
        setNotReady(true);
        setMessage(
          'Notification preferences are not ready yet (waiting on K5). Your choices were not saved.',
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
          Digests and execution alerts land in your inbox once the notify plane ships. Until
          then, saves return a clear not-ready state.
        </p>
      </div>

      <label className="block space-y-1">
        <span className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
          Email
        </span>
        <input
          type="email"
          className="w-full rounded-lg border border-hair bg-term-bg/50 px-3 py-2 text-sm text-ink"
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
          className="w-full rounded-lg border border-hair bg-term-bg/50 px-3 py-2 text-sm font-mono text-ink"
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
        disabled={busy}
        onClick={() => void onSave()}
        className="rounded-lg border border-accent/40 bg-accent/15 px-4 py-2 text-sm font-medium text-accent disabled:opacity-50"
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
    <label className="flex items-center justify-between gap-3 rounded-lg border border-hair bg-term-bg/40 px-3 py-2">
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
