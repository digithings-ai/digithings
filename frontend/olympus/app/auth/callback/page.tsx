'use client';

import { useEffect, useState } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { AtlasMark } from '@/components/atlas-mark';
import {
  getSupabaseClient,
  oauthCallbackErrorFromLocation,
  oauthPkceCodeFromLocation,
} from '@/lib/supabase';

const SIGN_IN_FAILED = 'Sign-in did not complete. Return to login and try again.';

function callbackErrorMessage(): string | null {
  if (typeof window === 'undefined') return null;
  return oauthCallbackErrorFromLocation(window.location.search, window.location.hash);
}

/**
 * OAuth PKCE callback (static page). Exchanges `?code=` into a session, then
 * routes home. Surfaces provider `error` / `error_description` (Google often
 * lands these when the client is disabled or the redirect allow-list misses).
 */
export default function AuthCallbackPage() {
  const router = useRouter();
  const client = getSupabaseClient();
  const [message, setMessage] = useState(() => {
    if (!client) return 'Supabase is not configured.';
    const err = callbackErrorMessage();
    if (err) return err;
    return 'Completing sign-in…';
  });
  const [failed, setFailed] = useState(() => Boolean(callbackErrorMessage()) || !client);

  useEffect(() => {
    if (!client) return;
    if (callbackErrorMessage()) return;

    let cancelled = false;
    let settled = false;

    const goHome = () => {
      if (cancelled || settled) return;
      settled = true;
      router.replace('/');
    };

    const fail = (reason: string) => {
      if (cancelled || settled) return;
      settled = true;
      setFailed(true);
      setMessage(reason);
    };

    const code = oauthPkceCodeFromLocation(window.location.search);
    if (code) {
      void client.auth.exchangeCodeForSession(code).then(({ error }) => {
        if (cancelled) return;
        if (!error) {
          goHome();
          return;
        }
        void client.auth.getSession().then(({ data }) => {
          if (cancelled) return;
          if (data.session) goHome();
          else fail(error.message || SIGN_IN_FAILED);
        });
      });
    } else {
      void client.auth.getSession().then(({ data, error }) => {
        if (cancelled) return;
        if (error) {
          fail(SIGN_IN_FAILED);
          return;
        }
        if (data.session) goHome();
      });
    }

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
    <div className="acct-login-shell qn-blueprint-bg">
      <div className="acct-login-card">
        <div className="acct-login-mark">
          <AtlasMark className="shrink-0" />
        </div>
        <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
          olympus <span className="text-ink-mute">· sign in</span>
        </p>
        <p className="mt-3 font-mono text-[0.78rem] text-ink-mute" role="status">
          {message}
        </p>
        {failed ? (
          <Link href="/login/" className="btn-ghost acct-btn-block text-center">
            Return to sign in
          </Link>
        ) : null}
      </div>
    </div>
  );
}
