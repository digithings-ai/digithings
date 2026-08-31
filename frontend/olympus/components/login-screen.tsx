'use client';

import { useState } from 'react';
import { AtlasMark } from '@/components/atlas-mark';
import { useAuth, type OAuthProvider } from '@/lib/auth-context';

/**
 * Full-page login for the digiquant dashboard (static-export PKCE). Google + GitHub only (D4).
 * Rendered by AuthGate when signed out, and by `/login`.
 */
export function LoginScreen() {
  const { signInWithOAuth, authEnabled } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [pending, setPending] = useState<OAuthProvider | null>(null);

  async function start(provider: OAuthProvider) {
    setError(null);
    setPending(provider);
    try {
      await signInWithOAuth(provider);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
      setPending(null);
    }
  }

  return (
    <div className="flex min-h-screen flex-col items-center justify-center bg-bg px-6 text-ink qn-blueprint-bg">
      <div className="w-full max-w-sm">
        <div className="mb-10 flex flex-col items-center gap-3 text-center">
          <AtlasMark className="shrink-0" />
          <h1 className="font-display text-2xl tracking-tight text-ink">digiquant</h1>
          <p className="text-sm text-ink-soft">
            Sign in to view your workspace. Sessions use Supabase Auth (Google or GitHub).
          </p>
        </div>

        {!authEnabled ? (
          <p className="border border-hair bg-surface/80 px-4 py-3 text-sm text-ink-mute">
            App auth is off. Set <code className="font-mono text-xs">NEXT_PUBLIC_OLYMPUS_AUTH=1</code>{' '}
            at build time to enable login.
          </p>
        ) : (
          <div className="flex flex-col gap-3">
            <button
              type="button"
              disabled={pending !== null}
              onClick={() => void start('google')}
              className="inline-flex items-center justify-center border border-hair bg-surface px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-ink/[0.06] disabled:opacity-60"
            >
              {pending === 'google' ? 'Redirecting…' : 'Continue with Google'}
            </button>
            <button
              type="button"
              disabled={pending !== null}
              onClick={() => void start('github')}
              className="inline-flex items-center justify-center border border-hair bg-surface px-4 py-2.5 text-sm font-medium text-ink transition-colors hover:bg-ink/[0.06] disabled:opacity-60"
            >
              {pending === 'github' ? 'Redirecting…' : 'Continue with GitHub'}
            </button>
          </div>
        )}

        {error ? (
          <p className="mt-4 text-sm text-down" role="alert">
            {error}
          </p>
        ) : null}
      </div>
    </div>
  );
}
