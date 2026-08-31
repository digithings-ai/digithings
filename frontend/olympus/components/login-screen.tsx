'use client';

import { useState, type FormEvent } from 'react';
import Link from 'next/link';
import { useRouter } from 'next/navigation';
import { DashboardMark } from '@/components/atlas-mark';
import { useAuth, type OAuthProvider } from '@/lib/auth-context';

const STRENGTH_WORDS = ['', 'weak', 'fair', 'good', 'strong'] as const;
/** Ink/accent/danger — not P&L `--up`/`--down`. */
const STRENGTH_COLORS = ['', 'var(--danger)', 'var(--accent)', 'var(--accent)', 'var(--ink)'] as const;
export const MIN_PASSWORD_LENGTH = 8;

function passwordStrength(password: string): number {
  if (password.length === 0) return 0;
  let score = 1;
  if (password.length >= MIN_PASSWORD_LENGTH) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password) || /[^a-zA-Z0-9]/.test(password)) score += 1;
  return Math.min(score, 4);
}

export type LoginScreenMode = 'signin' | 'signup';

/**
 * Full-page login / signup for the digiquant dashboard (static-export PKCE).
 * Grammar from digiweb account LoginCard / SignupCard (oauth-first).
 */
export function LoginScreen({ initialMode = 'signin' }: { initialMode?: LoginScreenMode }) {
  const router = useRouter();
  const { signInWithOAuth, signInWithPassword, signUpWithPassword, authEnabled } = useAuth();
  const [mode, setMode] = useState<LoginScreenMode>(initialMode);
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [pending, setPending] = useState<OAuthProvider | 'email' | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const score = passwordStrength(password);
  const signUp = mode === 'signup';

  async function start(provider: OAuthProvider) {
    setError(null);
    setInfo(null);
    setPending(provider);
    try {
      await signInWithOAuth(provider);
    } catch (err) {
      setError(err instanceof Error ? err.message : 'Sign-in failed');
      setPending(null);
    }
  }

  async function onEmailSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    setInfo(null);
    const trimmedEmail = email.trim();
    if (!trimmedEmail || password.length < MIN_PASSWORD_LENGTH) {
      setError(`Email and an ${MIN_PASSWORD_LENGTH}+ character password are required.`);
      return;
    }
    setPending('email');
    try {
      if (signUp) {
        await signUpWithPassword(trimmedEmail, password);
        setInfo('Check your email to confirm the account, then sign in.');
      } else {
        await signInWithPassword(trimmedEmail, password);
        router.replace('/');
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : signUp ? 'Sign-up failed' : 'Sign-in failed');
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="acct-login-shell qn-blueprint-bg">
      <div className="acct-login-card">
        <div className="acct-login-mark">
          <DashboardMark className="shrink-0" />
        </div>
        <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
          digiquant{' '}
          <span className="text-ink-mute">{signUp ? '· create account' : '· sign in'}</span>
        </p>
        <h1 className="mt-2 font-display text-[1.45rem] font-normal leading-[1.15] tracking-[-0.02em] text-ink">
          {signUp ? 'From zero to the desk.' : 'Open the desk.'}
        </h1>
        <p className="mt-2 text-[0.88rem] leading-[1.45] text-ink-soft">
          {signUp
            ? 'Google or GitHub to start. Email if you would rather keep a password.'
            : 'Google or GitHub. Email if you already have a workspace password.'}
        </p>

        {!authEnabled ? (
          <p className="mt-4 border border-hair bg-bg px-4 py-3 font-mono text-[0.68rem] text-ink-mute">
            App auth is off. Set <code>NEXT_PUBLIC_DASHBOARD_AUTH=1</code> at build time to enable
            login.
          </p>
        ) : (
          <>
            <button
              type="button"
              disabled={pending !== null}
              onClick={() => void start('google')}
              className="btn-primary acct-btn-block"
              data-testid="login-google"
            >
              {pending === 'google' ? 'Redirecting…' : 'Continue with Google'}
            </button>
            <button
              type="button"
              disabled={pending !== null}
              onClick={() => void start('github')}
              className="btn-ghost acct-btn-block"
              data-testid="login-github"
            >
              {pending === 'github' ? 'Redirecting…' : 'Continue with GitHub'}
            </button>

            <form onSubmit={(event) => void onEmailSubmit(event)}>
              <div className="acct-divider">
                <span>or email</span>
              </div>
              <div className="acct-field" style={{ marginTop: 0 }}>
                <label
                  className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                  htmlFor="acct-email"
                >
                  Email
                </label>
                <input
                  className={error ? 'acct-input acct-input-error' : 'acct-input'}
                  id="acct-email"
                  name="email"
                  type="email"
                  autoComplete="username"
                  required
                  value={email}
                  onChange={(event) => setEmail(event.target.value)}
                  placeholder="you@desk.tld"
                />
              </div>
              <div className="acct-field">
                <label
                  className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                  htmlFor="acct-password"
                >
                  Password
                </label>
                <input
                  className={error ? 'acct-input acct-input-error' : 'acct-input'}
                  id="acct-password"
                  name="password"
                  type="password"
                  autoComplete={signUp ? 'new-password' : 'current-password'}
                  required
                  minLength={MIN_PASSWORD_LENGTH}
                  value={password}
                  onChange={(event) => setPassword(event.target.value)}
                  placeholder={
                    signUp ? `${MIN_PASSWORD_LENGTH}+ chars, mixed case, a digit` : '••••••••••'
                  }
                  aria-describedby={signUp ? 'acct-strength' : undefined}
                />
                {signUp ? (
                  <div className="mt-2 flex items-center gap-[0.7rem]">
                    <div
                      className="grid flex-1 grid-cols-[repeat(4,minmax(0,1fr))] gap-[6px]"
                      aria-hidden="true"
                    >
                      {[0, 1, 2, 3].map((index) => (
                        <span
                          key={index}
                          className="acct-strength-seg"
                          style={index < score ? { background: STRENGTH_COLORS[score] } : undefined}
                        />
                      ))}
                    </div>
                    <span
                      className="min-w-[3.6rem] text-right font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                      id="acct-strength"
                      role="status"
                    >
                      {STRENGTH_WORDS[score] || '—'}
                    </span>
                  </div>
                ) : null}
              </div>
              <button
                type="submit"
                disabled={pending !== null}
                className="btn-ghost acct-btn-block"
                data-testid="login-email-submit"
              >
                {pending === 'email'
                  ? signUp
                    ? 'Creating…'
                    : 'Signing in…'
                  : signUp
                    ? 'Create account with email'
                    : 'Sign in with email'}
              </button>
            </form>

            <p className="mt-4 text-center font-mono text-[0.68rem] text-ink-mute">
              {signUp ? (
                <>
                  Already on the desk?{' '}
                  <Link
                    href="/login/"
                    className="text-ink underline-offset-2 hover:underline"
                    onClick={() => setMode('signin')}
                  >
                    Sign in
                  </Link>
                </>
              ) : (
                <>
                  New workspace?{' '}
                  <Link
                    href="/signup/"
                    className="text-ink underline-offset-2 hover:underline"
                    onClick={() => setMode('signup')}
                  >
                    Create an account
                  </Link>
                </>
              )}
            </p>
          </>
        )}

        {error ? (
          <p className="acct-error" role="alert">
            {error}
          </p>
        ) : null}
        {info ? (
          <p className="mt-3 font-mono text-[0.68rem] text-ink-soft" role="status">
            {info}
          </p>
        ) : null}
      </div>
    </div>
  );
}
