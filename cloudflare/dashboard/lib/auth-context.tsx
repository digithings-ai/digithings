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
  isDashboardAuthEnabled,
  oauthRedirectTo,
  oauthSignInOptions,
  type OAuthProvider,
} from './supabase';
import { formatAuthError, isDuplicateSignupUser } from './auth-errors';
import { clearStashedInvite } from './invite-stash';

export type { OAuthProvider };

export interface AuthContextValue {
  /** True when NEXT_PUBLIC_DASHBOARD_AUTH=1 at build time. */
  authEnabled: boolean;
  session: Session | null;
  user: User | null;
  /**
   * Session resolve in progress after mount (auth flag on only).
   * Always false during SSR/prerender so AuthGate can emit the full shell.
   */
  loading: boolean;
  signInWithOAuth: (provider: OAuthProvider) => Promise<void>;
  signInWithPassword: (email: string, password: string) => Promise<void>;
  /** Session is present when confirm-email is off; otherwise the caller must not claim mail arrived. */
  signUpWithPassword: (
    email: string,
    password: string,
  ) => Promise<{ session: Session | null }>;
  signOut: () => Promise<void>;
}

/** Exported so entitlement hooks can read session without throwing outside the tree. */
export const AuthContext = createContext<AuthContextValue | null>(null);

function missingClient(): Error {
  return new Error(
    'Supabase is not configured. Set NEXT_PUBLIC_SUPABASE_URL and NEXT_PUBLIC_SUPABASE_ANON_KEY.',
  );
}

export function AuthProvider({ children }: { children: ReactNode }) {
  const authEnabled = isDashboardAuthEnabled();
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
      throw missingClient();
    }
    const { data, error } = await client.auth.signInWithOAuth({
      provider,
      options: oauthSignInOptions(provider),
    });
    if (error) throw error;
    if (!data.url) {
      throw new Error(
        formatAuthError(
          provider === 'google'
            ? 'Google did not return a redirect URL. Enable the Google provider in Supabase Auth and add this origin to Redirect URLs.'
            : 'Sign-in did not return a redirect URL. Enable the provider in Supabase Auth.',
          'oauth',
        ),
      );
    }
    window.location.assign(data.url);
  }, []);

  const signInWithPassword = useCallback(async (email: string, password: string) => {
    const client = getSupabaseClient();
    if (!client) {
      throw missingClient();
    }
    const { error } = await client.auth.signInWithPassword({ email, password });
    if (error) throw error;
  }, []);

  const signUpWithPassword = useCallback(async (email: string, password: string) => {
    const client = getSupabaseClient();
    if (!client) {
      throw missingClient();
    }
    const { data, error } = await client.auth.signUp({
      email,
      password,
      options: { emailRedirectTo: oauthRedirectTo() },
    });
    if (error) throw error;
    if (isDuplicateSignupUser(data.user)) {
      throw new Error(
        formatAuthError(new Error('User already registered'), 'signup'),
      );
    }
    return { session: data.session };
  }, []);

  const signOut = useCallback(async () => {
    clearStashedInvite();
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
      signInWithPassword,
      signUpWithPassword,
      signOut,
    }),
    [
      authEnabled,
      session,
      loading,
      signInWithOAuth,
      signInWithPassword,
      signUpWithPassword,
      signOut,
    ],
  );

  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>;
}

export function useAuth(): AuthContextValue {
  const ctx = useContext(AuthContext);
  if (!ctx) throw new Error('useAuth must be used inside AuthProvider');
  return ctx;
}
