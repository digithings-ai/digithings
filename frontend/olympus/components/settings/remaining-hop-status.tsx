'use client';

import { useCallback, useEffect, useState } from 'react';
import {
  getFills,
  getJobs,
  getNotificationLog,
  getProfile,
  listBrokers,
  type SettingsApiOptions,
} from '@/lib/settings-api';
import {
  provenRemainingHops,
  REMAINING_HOP_LABELS,
  REMAINING_LIVE_HOPS,
  type RemainingHopEvidence,
  type RemainingHopProven,
} from '@/lib/remaining-hops';

export type RemainingHopStatusProps = {
  api: SettingsApiOptions | null;
  getProfileFn?: typeof getProfile;
  listBrokersFn?: typeof listBrokers;
  getJobsFn?: typeof getJobs;
  getFillsFn?: typeof getFills;
  getLogFn?: typeof getNotificationLog;
};

function evidenceFromPayloads(args: {
  subscription_status?: string | null;
  has_stripe_subscription?: boolean;
  connections: { broker: string; env: string; status: string; auth_kind?: string }[];
  jobs: { job_type: string; status: string }[];
  fills: { symbol: string }[];
  events: { event_key: string }[];
}): RemainingHopEvidence {
  return {
    subscription_status: args.subscription_status ?? null,
    has_stripe_subscription: args.has_stripe_subscription === true,
    connections: args.connections.map((row) => [
      row.broker,
      row.env,
      row.status,
      row.auth_kind ?? '',
    ]),
    jobs: args.jobs.map((row) => [row.job_type, row.status]),
    fill_count: args.fills.filter((row) => row.symbol.trim()).length,
    digest_event_keys: args.events.map((row) => row.event_key),
    digest_inbox_confirmed: false,
  };
}

export function RemainingHopStatus({
  api,
  getProfileFn = getProfile,
  listBrokersFn = listBrokers,
  getJobsFn = getJobs,
  getFillsFn = getFills,
  getLogFn = getNotificationLog,
}: RemainingHopStatusProps) {
  const [proven, setProven] = useState<RemainingHopProven | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [loading, setLoading] = useState(false);

  const hydrate = useCallback(async () => {
    if (!api) return;
    setLoading(true);
    setError(null);
    try {
      const [profile, connections, jobs, fills, events] = await Promise.all([
        getProfileFn(api).catch(() => null),
        listBrokersFn(api).catch(() => []),
        getJobsFn(api).catch(() => []),
        getFillsFn(api).catch(() => []),
        getLogFn(api).catch(() => []),
      ]);
      setProven(
        provenRemainingHops(
          evidenceFromPayloads({
            subscription_status: profile?.subscription_status,
            has_stripe_subscription: profile?.has_stripe_subscription,
            connections,
            jobs,
            fills,
            events,
          }),
        ),
      );
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Unable to load remaining hops.');
      setProven(null);
    } finally {
      setLoading(false);
    }
  }, [api, getProfileFn, listBrokersFn, getJobsFn, getFillsFn, getLogFn]);

  useEffect(() => {
    /* eslint-disable react-hooks/set-state-in-effect -- hydrate hops after mount */
    void hydrate();
    /* eslint-enable react-hooks/set-state-in-effect */
  }, [hydrate]);

  return (
    <div className="space-y-2" data-testid="remaining-hop-status">
      <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
        Remaining hops
      </p>
      <p className="text-xs text-ink-mute">
        Member-scoped Settings reads only. House <span className="font-mono">active</span> without
        a Stripe subscription boolean does not prove checkout. Digest log without inbox
        confirmation does not prove received.
      </p>
      {!api ? (
        <p className="text-sm text-ink-mute">Sign in to load remaining hops.</p>
      ) : null}
      {loading ? (
        <p className="text-sm text-ink-mute" data-testid="remaining-hop-loading">
          Loading remaining hops…
        </p>
      ) : null}
      {error ? (
        <p className="text-sm text-down" role="alert">
          {error}
        </p>
      ) : null}
      {proven ? (
        <ul className="divide-y divide-hair border border-hair">
          {REMAINING_LIVE_HOPS.map((hop) => (
            <li
              key={hop}
              className="flex items-center justify-between gap-3 px-3 py-2 text-sm"
              data-testid={`remaining-hop-${hop}`}
              data-proven={proven[hop] ? 'true' : 'false'}
            >
              <span className="text-ink-soft">{REMAINING_HOP_LABELS[hop]}</span>
              <span className="font-mono text-xs text-ink-mute">
                {proven[hop] ? 'proven' : 'unproven'}
              </span>
            </li>
          ))}
        </ul>
      ) : null}
    </div>
  );
}
