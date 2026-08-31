/**
 * Honest Auth copy for Olympus login + signup.
 *
 * Email confirmation uses Supabase Auth SMTP (or Cloudflare Access PIN on
 * staging). Neither is Mailgun digest. Until custom Auth SMTP is wired, the
 * confirmation message / 6-digit code often never arrives — OAuth is the
 * working create-account path (first-time Google/GitHub *is* signup).
 */

export const CONFIRM_EMAIL_COPY =
  'Email confirmation is on, but Auth SMTP is not delivering yet, so the message or 6-digit code often never arrives. Continue with Google or GitHub instead — first-time OAuth creates the account. If Google is disabled in the Auth dashboard, use GitHub.';

export const SIGNUP_SESSION_MISSING_COPY = CONFIRM_EMAIL_COPY;

export type AuthErrorKind = 'signin' | 'signup' | 'oauth';

function messageOf(err: unknown): string {
  if (err instanceof Error && err.message.trim()) return err.message;
  if (typeof err === 'string' && err.trim()) return err;
  return '';
}

/** Map supabase-js / provider errors to operator-actionable copy. Never leak secrets. */
export function formatAuthError(err: unknown, kind: AuthErrorKind): string {
  const raw = messageOf(err);
  const lower = raw.toLowerCase();

  if (
    lower.includes('provider is not enabled') ||
    lower.includes('unsupported provider')
  ) {
    if (lower.includes('google') || kind === 'oauth') {
      return 'Google is not enabled on this project yet. Use GitHub, or ask the operator to enable the Google provider in Supabase Auth (Authentication → Providers) and add this origin to Redirect URLs.';
    }
    return 'That sign-in provider is not enabled yet. Use GitHub, or ask the operator to enable it in Supabase Auth.';
  }

  if (lower.includes('email not confirmed') || lower.includes('email_not_confirmed')) {
    return CONFIRM_EMAIL_COPY;
  }

  if (
    lower.includes('user already registered') ||
    lower.includes('already registered') ||
    lower.includes('already been registered')
  ) {
    return 'An account with that email already exists. Sign in, or continue with Google or GitHub.';
  }

  if (lower.includes('invalid login credentials')) {
    return 'Email or password is wrong. If you just created the account, confirmation mail may not have arrived — use Google or GitHub instead.';
  }

  if (raw) return raw;
  if (kind === 'signup') return 'Sign-up failed';
  if (kind === 'oauth') return 'Sign-in failed';
  return 'Sign-in failed';
}

/**
 * Supabase returns a user with empty identities and no session when the
 * email is already registered and confirm-email is on (no error object).
 */
export function isDuplicateSignupUser(user: {
  identities?: readonly unknown[] | null;
} | null): boolean {
  if (!user) return false;
  return !user.identities || user.identities.length === 0;
}
