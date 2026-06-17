'use client';

import { createContext, useContext, useState, useEffect, ReactNode } from 'react';
import { getFullDashboardData } from './queries';
import type { DashboardData } from './types';

interface DashboardContextValue {
  data: DashboardData | null;
  loading: boolean;
  error: string | null;
}

const DashboardContext = createContext<DashboardContextValue | null>(null);

export function DashboardProvider({ children }: { children: ReactNode }) {
  const [data, setData] = useState<DashboardData | null>(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    getFullDashboardData()
      .then(setData)
      .catch((err: unknown) =>
        setError(
          err instanceof Error ? err.message : 'Failed to load data'
        )
      )
      .finally(() => setLoading(false));
  }, []);

  return (
    <DashboardContext.Provider value={{ data, loading, error }}>
      {children}
    </DashboardContext.Provider>
  );
}

export function useDashboard(): DashboardContextValue {
  const ctx = useContext(DashboardContext);
  if (!ctx) throw new Error('useDashboard must be used inside DashboardProvider');
  return ctx;
}
