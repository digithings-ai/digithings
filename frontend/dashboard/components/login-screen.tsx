'use client';

import { useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { AuthCard, type AuthOAuthProvider } from '@digithings/web';
import { useAuth } from '@/lib/auth-context';
import { formatAuthError, SIGNUP_SESSION_MISSING_COPY } from '@/lib/auth-errors';
import { dashboardBasePath } from '@/lib/supabase';

export const MIN_PASSWORD_LENGTH = 8;

export type LoginScreenMode = 'signin' | 'signup';

/**
 * Full-page login / signup for the digiquant dashboard (static-export PKCE).
 * Compact AuthCard from @digithings/web: mark + digiquant wordmark, email,
 * password, icon OAuth row + Sign in / Sign up.
 */
export function LoginScreen({ initialMode = 'signin' }: { initialMode?: LoginScreenMode }) {
  const router = useRouter();
  const { signInWithOAuth, signInWithPassword, signUpWithPassword, authEnabled } = useAuth();
  const [error, setError] = useState<string | null>(null);
  const [info, setInfo] = useState<string | null>(null);
  const [pending, setPending] = useState<AuthOAuthProvider | 'email' | null>(null);
  const [email, setEmail] = useState('');
  const [password, setPassword] = useState('');
  const signUp = initialMode === 'signup';
  const base = dashboardBasePath();

  async function start(provider: AuthOAuthProvider) {
    setError(null);
    setInfo(null);
    setPending(provider);
    try {
      await signInWithOAuth(provider);
    } catch (err) {
      setError(formatAuthError(err, 'oauth'));
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
        const { session } = await signUpWithPassword(trimmedEmail, password);
        if (session) {
          router.replace('/');
        } else {
          setInfo(SIGNUP_SESSION_MISSING_COPY);
        }
      } else {
        await signInWithPassword(trimmedEmail, password);
        router.replace('/');
      }
    } catch (err) {
      setError(formatAuthError(err, signUp ? 'signup' : 'signin'));
    } finally {
      setPending(null);
    }
  }

  return (
    <div className="acct-login-shell qn-blueprint-bg">
      {!authEnabled ? (
        <div className="acct-login-card">
          <p className="font-mono text-[0.68rem] text-ink-mute">
            App auth is off. Set <code>NEXT_PUBLIC_DASHBOARD_AUTH=1</code> at build time to enable
            login.
          </p>
        </div>
      ) : (
        <AuthCard
          layout="compact"
          mode={signUp ? 'signup' : 'signin'}
          productName="digiquant"
          email={email}
          password={password}
          onEmailChange={setEmail}
          onPasswordChange={setPassword}
          onSubmit={(event) => {
            void onEmailSubmit(event);
          }}
          onOAuth={(provider) => {
            void start(provider);
          }}
          pending={pending}
          error={error}
          info={info}
          switchHref={signUp ? `${base}/login/` : `${base}/signup/`}
          idPrefix="acct"
        />
      )}
    </div>
  );
}
