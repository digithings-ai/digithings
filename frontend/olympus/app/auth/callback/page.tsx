'use client';

import { useEffect, useState } from 'react';
import { useRouter } from 'next/navigation';
import { getSupabaseClient } from '@/lib/supabase';

/**
 * OAuth PKCE callback (static page). supabase-js detects the URL code,
 * exchanges it into a session, then we route home. No Next route handler.
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const client = getSupabaseClient();
  const [message, setMessage] = useState(() =>
    client ? 'Completing sign-in…' : 'Supabase is not configured.',
  );

  useEffect(() => {
    if (!client) return;

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
        setMessage(error.message);
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

    const timer = window.setTimeout(() => {
      if (cancelled || settled) return;
      void client.auth.getSession().then(({ data }) => {
        if (cancelled || settled) return;
        if (data.session) {
          goHome();
        } else {
          setMessage('Sign-in did not complete. Return to login and try again.');
        }
      });
    }, 2500);

    return () => {
      cancelled = true;
      window.clearTimeout(timer);
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
