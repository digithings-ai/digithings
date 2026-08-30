'use client';

import {
  createContext,
  useCallback,
  useContext,
  useEffect,
  useMemo,
  useState,
  type ReactNode,
} from 'react';
import type { Session, User } from '@supabase/supabase-js';
import {
  getSupabaseClient,
  isOlympusAuthEnabled,
  oauthRedirectTo,
} from './supabase';

export type OAuthProvider = 'google' | 'github';

export interface AuthContextValue {
  /** True when NEXT_PUBLIC_OLYMPUS_AUTH=1 (build-time). */
  authEnabled: boolean;
  session: Session | null;
  user: User | null;
  /**
   * Session resolve in progress after mount (auth flag on only).
   * Always false during SSR/prerender so AuthGate can emit the full shell.
   */
  loading: boolean;
  signInWithOAuth: (provider: OAuthProvider) => Promise<void>;
  signOut: () => Promise<void>;
}

/** Exported so entitlement hooks can read session without throwing outside the tree. */
export const AuthContext = createContext<AuthContextValue | null>(null);

const SIGN_IN_FAILED = 'Sign-in did not complete. Return to login and try again.';

export function AuthProvider({ children }: { children: ReactNode }) {
  const authEnabled = isOlympusAuthEnabled();
  const [session, setSession] = useState<Session | null>(null);
  // Start false so static prerender never collapses to a loading screen.
  const [loading, setLoading] = useState(false);

  useEffect(() => {
    if (!authEnabled) {
      return;
    }
    const client = getSupabaseClient();
    if (!client) {
      return;
    }

    let cancelled = false;
    /* eslint-disable react-hooks/set-state-in-effect -- begin session resolve after mount only */
    setLoading(true);
    /* eslint-enable react-hooks/set-state-in-effect */

    client.auth.getSession().then(({ data }) => {
      if (cancelled) return;
      setSession(data.session);
      setLoading(false);
    });

    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((_event, next) => {
      setSession(next);
      setLoading(false);
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [authEnabled]);

  const signInWithOAuth = useCallback(async (provider: OAuthProvider) => {
    const client = getSupabaseClient();
    if (!client) {
      throw new Error(
        'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.',
      );
    }
    const { error } = await client.auth.signInWithOAuth({
      provider,
      options: { redirectTo: oauthRedirectTo() },
    });
    if (error) throw error;
  }, []);

  const signOut = useCallback(async () => {
    const client = getSupabaseClient();
    if (!client) {
      setSession(null);
      return;
    }
    const { error } = await client.auth.signOut();
    if (error) throw error;
    setSession(null);
  }, []);

  const value = useMemo<AuthContextValue>(
    () => ({
      authEnabled,
      session,
      user: session?.user ?? null,
      loading,
      signInWithOAuth,
      signOut,
    }),
    [authEnabled, session, loading, signInWithOAuth, signOut],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
