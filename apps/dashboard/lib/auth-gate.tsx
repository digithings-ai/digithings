'use client';

import { useEffect, useSyncExternalStore, type ReactNode } from 'react';
import { usePathname, useRouter } from 'next/navigation';
import { DashboardProvider } from '@/lib/dashboard-context';
import { AppShellProvider } from '@/components/app-shell-context';
import AppFrame from '@/components/app-frame';
import { LoginScreen } from '@/components/login-screen';
import { useAuth } from '@/lib/auth-context';
import { hasPendingInvite } from '@/lib/invite-stash';
import { useInviteLink } from '@/lib/invite-link';
import { useAccessPending } from '@/lib/use-entitlement';

/** Exact auth routes (Next usePathname strips basePath). */
const AUTH_PATHS = new Set(['/login', '/signup', '/auth/callback']);

/** Prefixed forms if a caller ever passes a full path including basePath. */
const AUTH_PATHS_WITH_BASE = new Set([
  '/dashboard/login',
  '/dashboard/signup',
  '/dashboard/auth/callback',
]);

/**
 * Paths that complete or start OAuth without a session (no dashboard chrome).
 * Exact match only — `/settings/login` must NOT bypass.
 */
export function isDashboardAuthPath(pathname: string | null): boolean {
  const norm = (pathname ?? '').replace(/\/+$/, '') || '/';
  return AUTH_PATHS.has(norm) || AUTH_PATHS_WITH_BASE.has(norm);
}

/** PKCE callback only — must run even when a session already exists. */
export function isDashboardAuthCallbackPath(pathname: string | null): boolean {
  const norm = (pathname ?? '').replace(/\/+$/, '') || '/';
  return (
    norm === '/auth/callback' ||
    norm === '/dashboard/auth/callback'
  );
}

function SignedInAuthPathRedirect() {
  const router = useRouter();
  useEffect(() => {
    router.replace('/');
  }, [router]);
  return <AuthLoadingScreen />;
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
 * - Flag on + `/login` or `/signup` with a session → replace home (email
 *   sign-in would otherwise sit on the card; callback is excluded so PKCE
 *   can finish).
 * - Flag on + not yet mounted → full shell (prerender-safe; static export keeps <h1>).
 * - Flag on + mounted + loading → loading screen (never empty chrome).
 * - Flag on + mounted + no session → LoginScreen (signup-first if a pending
 *   invite is in the URL/stash, sign-in otherwise).
 * - Flag on + mounted + session → AppProviders + children.
 */
export function AuthGate({ children }: { children: ReactNode }) {
  const { authEnabled, session, loading } = useAuth();
  const pathname = usePathname();
  const mounted = useHasMounted();
  const { pending: invitePending } = useInviteLink();
  const accessPending = useAccessPending();

  if (!authEnabled) {
    return <AppProviders>{children}</AppProviders>;
  }

  if (isDashboardAuthCallbackPath(pathname)) {
    return <>{children}</>;
  }

  if (isDashboardAuthPath(pathname)) {
    if (mounted && !loading && session) {
      return <SignedInAuthPathRedirect />;
    }
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
    // An invite link is how a visitor without an account arrives — default
    // them to signup, not sign-in, so the link is one click, not two.
    return <LoginScreen initialMode={hasPendingInvite() ? 'signup' : 'signin'} />;
  }

  // Hold the shell until `my_access` (and any stashed invite redeem) settle:
  // a 12x FX-Hub-only invitee must never flash the full DigiQuant chrome.
  if (accessPending || invitePending) {
    return <AuthLoadingScreen />;
  }

  return <AppProviders>{children}</AppProviders>;
}
