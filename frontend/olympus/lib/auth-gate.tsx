'use client';

import { useSyncExternalStore, type ReactNode } from 'react';
import { usePathname } from 'next/navigation';
import { DashboardProvider } from '@/lib/dashboard-context';
import { AppShellProvider } from '@/components/app-shell-context';
import AppFrame from '@/components/app-frame';
import { LoginScreen } from '@/components/login-screen';
import { useAuth } from '@/lib/auth-context';

/** Exact auth routes (Next usePathname strips basePath). */
const AUTH_PATHS = new Set(['/login', '/signup', '/auth/callback']);

/** Prefixed forms if a caller ever passes a full path including basePath. */
const AUTH_PATHS_WITH_BASE = new Set([
  '/olympus/login',
  '/olympus/signup',
  '/olympus/auth/callback',
]);

/**
 * Paths that complete or start OAuth without a session (no dashboard chrome).
 * Exact match only — `/settings/login` must NOT bypass.
 */
export function isOlympusAuthPath(pathname: string | null): boolean {
  const norm = (pathname ?? '').replace(/\/+$/, '') || '/';
  return AUTH_PATHS.has(norm) || AUTH_PATHS_WITH_BASE.has(norm);
}

/** false during SSR/prerender; true after client hydrate. */
function useHasMounted(): boolean {
  return useSyncExternalStore(
    () => () => {},
    () => true,
    () => false,
  );
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
 * - Flag on + not yet mounted → full shell (prerender-safe; static export keeps <h1>).
 * - Flag on + mounted + loading → loading screen (never empty chrome).
 * - Flag on + mounted + no session → LoginScreen.
 * - Flag on + mounted + session → AppProviders + children.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { authEnabled, session, loading } = useAuth();
  const pathname = usePathname();
  const mounted = useHasMounted();

  if (!authEnabled) {
    return <AppProviders>{children}</AppProviders>;
  }

  if (isOlympusAuthPath(pathname)) {
    return <>{children}</>;
  }

  // Prerender / SSR: emit the real page shell so check-static-export sees <h1>.
  // Gate only after mount once session resolve has had a chance to run.
  if (!mounted) {
    return <AppProviders>{children}</AppProviders>;
  }

  if (loading) {
    return <AuthLoadingScreen />;
  }

  if (!session) {
    return <LoginScreen />;
  }

  return <AppProviders>{children}</AppProviders>;
}
