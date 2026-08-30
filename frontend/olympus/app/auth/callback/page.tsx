'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getSupabaseClient } from '@/lib/supabase';

const SIGN_IN_FAILED = 'Sign-in did not complete. Return to login and try again.';

function urlHasOAuthError(): boolean {
  if (typeof window === 'undefined') return false;
  const search = new URLSearchParams(window.location.search);
  if (search.get('error')) return true;
  const hash = window.location.hash.startsWith('#')
    ? window.location.hash.slice(1)
    : window.location.hash;
  if (!hash) return false;
  return Boolean(new URLSearchParams(hash).get('error'));
}

/**
 * OAuth PKCE callback (static page). supabase-js detects the URL code,
 * exchanges it into a session, then we route home. No Next route handler.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const client = getSupabaseClient();
  const [message, setMessage] = useState(() => {
    if (!client) return 'Supabase is not configured.';
    if (urlHasOAuthError()) return SIGN_IN_FAILED;
    return 'Completing sign-in…';
  });

  useEffect(() => {
    if (!client) return;
    if (urlHasOAuthError()) return;

    let cancelled = false;
    let settled = false;

    const goHome = () => {
      if (cancelled || settled) return;
      settled = true;
      router.replace('/');
    };

    void client.auth.getSession().then(({ data, error }) => {
      if (cancelled) return;
      if (error) {
        setMessage(SIGN_IN_FAILED);
        return;
      }
      if (data.session) goHome();
    });

    const {
      data: { subscription },
    } = client.auth.onAuthStateChange((event, session) => {
      if (cancelled) return;
      if (
        session &&
        (event === 'SIGNED_IN' || event === 'INITIAL_SESSION' || event === 'TOKEN_REFRESHED')
      ) {
        goHome();
      }
    });

    return () => {
      cancelled = true;
      subscription.unsubscribe();
    };
  }, [client, router]);

  return (
    <div className="flex min-h-screen items-center justify-center bg-bg px-6 text-ink qn-blueprint-bg">
      <p className="font-mono text-sm text-ink-mute" role="status">
        {message}
      </p>
    </div>
  );
}
