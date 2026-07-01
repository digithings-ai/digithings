'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { getFullDashboardData } from './queries';
import { isSupabaseConfigured } from './supabase';
import type { DashboardData } from './types';

/**
 * Reachability of the live data backend, derived from what the provider already
 * knows — no extra fetch:
 *   - 'unconfigured': Supabase env is absent (no client could be built).
 *   - 'unreachable':  the dashboard fetch rejected.
 *   - 'ok':           configured and either still loading or resolved cleanly.
 * The three values are kept distinct so System/Settings can surface the precise
 * cause later; the DB-down gate (app-frame) treats unconfigured == unreachable.
 */
export type DbStatus = 'ok' | 'unconfigured' | 'unreachable';

interface DashboardContextValue {
  data: DashboardData | null;
  loading: boolean;
  error: string | null;
  dbStatus: DbStatus;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);
  const [reachable, setReachable] = useState(true);

  useEffect(() => {
    getFullDashboardData()
      .then(setData)
      .catch((err: unknown) => {
        setReachable(false);
        setError(err instanceof Error ? err.message : 'Failed to load data');
      })
      .finally(() => setLoading(false));
  }, []);

  // Unconfigured wins immediately and regardless of loading. Otherwise we stay
  // 'ok' while loading so the gate never flashes during normal startup, and only
  // flip to 'unreachable' once the fetch has actually rejected.
  const dbStatus: DbStatus = !isSupabaseConfigured()
    ? 'unconfigured'
    : reachable
      ? 'ok'
      : 'unreachable';

  return (
    <DashboardContext.Provider value={{ data, loading, error, dbStatus }}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error('useDashboard must be used inside DashboardProvider');
  return ctx;
}

/** Convenience selector for surfaces that only care about backend reachability. */
export function useDbStatus(): DbStatus {
  return useDashboard().dbStatus;
}
