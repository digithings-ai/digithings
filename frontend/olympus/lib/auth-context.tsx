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
  /** Initial session resolve in progress (auth flag on only). */
  loading: boolean;
  signInWithOAuth: (provider: OAuthProvider) => Promise<void>;
  signOut: () => Promise<void>;
}

const AuthContext = createContext<AuthContextValue | null>(null);

export function AuthProvider({ children }: { children: ReactNode }) {
  const authEnabled = isOlympusAuthEnabled();
  const [session, setSession] = useState<Session | null>(null);
  const [loading, setLoading] = useState(authEnabled);

  useEffect(() => {
    if (!authEnabled) {
      return;
    }
    const client = getSupabaseClient();
    if (!client) {
      /* eslint-disable react-hooks/set-state-in-effect -- no client: end loading without hanging the gate */
      setLoading(false);
      /* eslint-enable react-hooks/set-state-in-effect */
      return;
    }

    let cancelled = false;
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
