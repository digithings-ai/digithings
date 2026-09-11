import { describe, expect, it } from 'vitest';
import {
  CONFIRM_EMAIL_COPY,
  formatAuthError,
  isDuplicateSignupUser,
} from './auth-errors';

describe('formatAuthError', () => {
  it('maps a disabled Google provider to dashboard work, not an app bug', () => {
    const msg = formatAuthError(
      new Error('Unsupported provider: provider is not enabled'),
      'oauth',
    );
    expect(msg).toMatch(/Google is not enabled/i);
    expect(msg).toMatch(/GitHub/);
    expect(msg).toMatch(/Authentication → Providers/);
  });

  it('maps email_not_confirmed to the SMTP-honest copy', () => {
    expect(formatAuthError(new Error('Email not confirmed'), 'signin')).toBe(
      CONFIRM_EMAIL_COPY,
    );
  });

  it('maps already-registered without inventing a confirmation email', () => {
    const msg = formatAuthError(new Error('User already registered'), 'signup');
    expect(msg).toMatch(/already exists/i);
    expect(msg).not.toMatch(/check your email/i);
  });

  it('falls back to the raw message when it is already useful', () => {
    expect(formatAuthError(new Error('Password should be at least 8 characters'), 'signup')).toBe(
      'Password should be at least 8 characters',
    );
  });
});

describe('isDuplicateSignupUser', () => {
  it('treats empty identities as an existing account', () => {
    expect(isDuplicateSignupUser({ identities: [] })).toBe(true);
    expect(isDuplicateSignupUser({ identities: null })).toBe(true);
  });

  it('treats a real identity list as a new signup', () => {
    expect(isDuplicateSignupUser({ identities: [{ provider: 'email' }] })).toBe(false);
  });
});
