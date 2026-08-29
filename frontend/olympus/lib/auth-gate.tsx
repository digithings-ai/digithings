'use client';

import type { ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { DashboardProvider } from '@/lib/dashboard-context';
import { AppShellProvider } from '@/components/app-shell-context';
import AppFrame from '@/components/app-frame';
import { LoginScreen } from '@/components/login-screen';
import { useAuth } from '@/lib/auth-context';

/** Paths that complete or start OAuth without a session (no dashboard chrome). */
export function isOlympusAuthPath(pathname: string | null): boolean {
  const norm = (pathname ?? '').replace(/\/+$/, '') || '/';
  return norm === '/login' || norm === '/auth/callback' || norm.endsWith('/login') || norm.endsWith('/auth/callback');
}

function AppProviders({ children }: { children: ReactNode }) {
  return (
    <DashboardProvider>
      <AppShellProvider>
        <AppFrame>{children}</AppFrame>
      </AppShellProvider>
    </DashboardProvider>
  );
}

function AuthLoadingScreen() {
  return (
    <div className="flex min-h-screen items-center justify-center bg-bg text-ink">
      <p className="font-mono text-sm text-ink-mute">Checking session…</p>
    </div>
  );
}

/**
 * Flag-aware auth guard (T1).
 * - Flag off → AppProviders + children (today's shell).
 * - Flag on + auth route → children only (login / PKCE callback, no chrome).
 * - Flag on + loading → loading screen (never empty chrome).
 * - Flag on + no session → LoginScreen.
 * - Flag on + session → AppProviders + children.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { authEnabled, session, loading } = useAuth();
  const pathname = usePathname();

  if (!authEnabled) {
    return <AppProviders>{children}</AppProviders>;
  }

  if (isOlympusAuthPath(pathname)) {
    return <>{children}</>;
  }

  if (loading) {
    return <AuthLoadingScreen />;
  }

  if (!session) {
    return <LoginScreen />;
  }

  return <AppProviders>{children}</AppProviders>;
}
