'use client';

import { useContext, useState, type FormEvent, type ReactNode } from 'react';
import Link from 'next/link';
import { Lock } from 'lucide-react';
import { AuthContext } from '@/lib/auth-context';
import { useCanAccessProduct, requestAccessRefresh } from '@/lib/use-entitlement';
import { isOlympusAuthEnabled } from '@/lib/supabase';
import { redeemInvite, SettingsHttpError } from '@/lib/settings-api';

/**
 * Gate a custom Olympus client product (FX Hub now; future products reuse this).
 * Presentation only — data plane must still deny via RLS / dedicated project keys.
 *
 * After login, a hashed invite (settings EF) can INSERT `client_product_grants`
 * for the caller's email. The invite is not a login-optional passphrase.
 */
export function ClientProductGate({
  productKey,
  children,
  title = 'Client product',
  body = 'This surface is available to allowlisted client emails. Contact the operator if you expected access.',
}: {
  productKey: string;
  children: ReactNode;
  title?: string;
  body?: string;
}) {
  const allowed = useCanAccessProduct(productKey);
  const session = useContext(AuthContext)?.session ?? null;
  const [code, setCode] = useState('');
  const [pending, setPending] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [unlocked, setUnlocked] = useState(false);

  if (!isOlympusAuthEnabled() || allowed || unlocked) {
    return <>{children}</>;
  }

  async function onRedeem(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setError(null);
    const token = session?.access_token;
    if (!token) {
      setError('Sign in first, then enter the invite code.');
      return;
    }
    const trimmed = code.trim();
    if (trimmed.length < 10) {
      setError('Invite code is not valid.');
      return;
    }
    setPending(true);
    try {
      await redeemInvite(
        { accessToken: token },
        { code: trimmed, product_key: productKey },
      );
      setUnlocked(true);
      requestAccessRefresh();
    } catch (err) {
      if (err instanceof SettingsHttpError) {
        setError(err.message);
      } else {
        setError('Invite redeem failed.');
      }
    } finally {
      setPending(false);
    }
  }

  return (
    <section
      data-testid="client-product-locked"
      data-product-key={productKey}
      className="m-6 border border-hair bg-term-bg/50 px-4 py-5"
    >
      <div className="flex items-start gap-3">
        <span
          className="mt-0.5 flex h-8 w-8 shrink-0 items-center justify-center border border-accent/30 bg-accent/10 text-accent"
          aria-hidden
        >
          <Lock size={14} />
        </span>
        <div className="min-w-0 space-y-2">
          <p className="text-[10px] font-medium uppercase tracking-widest text-ink-mute">
            {title}
          </p>
          <p className="text-sm text-ink-soft">{body}</p>
          <form
            className="space-y-2 pt-1"
            onSubmit={(event) => void onRedeem(event)}
            data-testid="client-product-invite-form"
          >
            <label
              className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
              htmlFor="fx-hub-invite"
            >
              Team invite code
            </label>
            <input
              id="fx-hub-invite"
              name="invite"
              type="text"
              autoComplete="off"
              spellCheck={false}
              value={code}
              onChange={(event) => setCode(event.target.value)}
              placeholder="Paste the code the operator shared"
              className="acct-input w-full max-w-md"
              data-testid="client-product-invite-input"
            />
            <button
              type="submit"
              disabled={pending}
              className="btn-ghost"
              data-testid="client-product-invite-submit"
            >
              {pending ? 'Checking…' : 'Redeem invite'}
            </button>
          </form>
          {error ? (
            <p className="acct-error" role="alert">
              {error}
            </p>
          ) : null}
          <Link
            href="/settings#billing"
            className="inline-flex items-center text-sm font-medium text-accent transition-colors hover:underline"
          >
            Settings → Billing
          </Link>
        </div>
      </div>
    </section>
  );
}
