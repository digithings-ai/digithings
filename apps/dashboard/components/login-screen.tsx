'use client';

import { useEffect, useState, type FormEvent } from 'react';
import { useRouter } from 'next/navigation';
import { AuthCard, type AuthCardBrand, type AuthOAuthProvider } from '@digithings/ui';
import { Card } from '@digithings/ui/ui';
import { useAuth } from '@/lib/auth-context';
import { formatAuthError, SIGNUP_SESSION_MISSING_COPY } from '@/lib/auth-errors';
import { getInviteBrand } from '@/lib/settings-api';
import { parseInviteQuery, peekStashedInvite } from '@/lib/invite-stash';
import { dashboardBasePath } from '@/lib/supabase';

export const MIN_PASSWORD_LENGTH = 8;

export type LoginScreenMode = 'signin' | 'signup';

/**
 * Full-page login / signup for the digiquant dashboard (static-export PKCE).
 * Compact AuthCard from @digithings/ui: mark + digiquant wordmark, email,
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
  const [brand, setBrand] = useState<AuthCardBrand | null>(null);

  // Invite banner (signup only): the team marker is the only per-invite
  // variable — the line is a fixed generic template, no custom copy needed.
  const inviteBannerLine =
    "Create your account to get started. Your invite unlocks your team's workspace.";

  // Invite branding (signup only): an invite link is how someone WITHOUT an
  // account arrives, so resolve the client's marker for the card. Unbranded
  // or failed lookups keep the default card — getInviteBrand never rejects.
  useEffect(() => {
    if (!signUp || typeof window === 'undefined') return;
    const code = peekStashedInvite() ?? parseInviteQuery(window.location.search);
    if (!code) return;
    let cancelled = false;
    void getInviteBrand({}, { code }).then((result) => {
      if (!cancelled && result.marker) setBrand({ marker: result.marker, line: result.line });
    });
    return () => {
      cancelled = true;
    };
  }, [signUp]);

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
    <div className="qn-blueprint-bg flex min-h-screen flex-col items-center justify-center p-6 text-ink">
      {signUp && brand ? (
        <div className="acct-invite-banner" role="status">
          <span className="acct-invite-banner-marker">Join {brand.marker} on digiquant</span>
          <span className="acct-invite-banner-line">{inviteBannerLine}</span>
        </div>
      ) : null}
      {!authEnabled ? (
        <Card className="w-full max-w-[380px] gap-0 border border-hair p-5 ring-0">
          <p className="font-mono text-[0.68rem] text-ink-mute">
            App auth is off. Set <code>NEXT_PUBLIC_DASHBOARD_AUTH=1</code> at build time to enable
            login.
          </p>
        </Card>
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
