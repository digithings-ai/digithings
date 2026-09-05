/** AuthCard — the shared sign-in / create-account card. Layouts `compact`,
 *  `icons-first`, and `desk` share one email + password form with Google /
 *  GitHub / X OAuth. Dress lives in `./styles/account-auth.css` (`.acct-*`);
 *  the sign-up strength meter renders on desk-signup only. Consumers: the
 *  dashboard login screen (compact) and the reference account-page specimens.
 */
"use client";

import { type FormEvent, type ReactNode } from "react";
import { DigiquantMark } from "../symbols/marks";
import { GitHubGlyph, GoogleGlyph, XGlyph } from "../icons";

export type AuthCardLayout = "compact" | "icons-first" | "desk";
export type AuthCardMode = "signin" | "signup";
/** Supabase OAuth 2.0 id for X is `x` (not legacy `twitter`). UI copy is X. */
export type AuthOAuthProvider = "google" | "github" | "x";

const STRENGTH_WORDS = ["", "weak", "fair", "good", "strong"] as const;
const STRENGTH_COLORS = ["", "var(--danger)", "var(--accent)", "var(--accent)", "var(--ink)"] as const;

export function passwordStrength(password: string): number {
  if (password.length === 0) return 0;
  let score = 1;
  if (password.length >= 8) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password) || /[^a-zA-Z0-9]/.test(password)) score += 1;
  return Math.min(score, 4);
}

export type AuthCardProps = {
  layout: AuthCardLayout;
  mode?: AuthCardMode;
  productName?: string;
  mark?: ReactNode;
  email?: string;
  password?: string;
  onEmailChange?: (value: string) => void;
  onPasswordChange?: (value: string) => void;
  onSubmit?: (event: FormEvent<HTMLFormElement>) => void;
  onOAuth?: (provider: AuthOAuthProvider) => void;
  onForgotPassword?: () => void;
  pending?: AuthOAuthProvider | "email" | null;
  error?: string | null;
  info?: string | null;
  switchHref?: string;
  idPrefix?: string;
};

const OAUTH: { provider: AuthOAuthProvider; label: string; testId: string; icon: ReactNode }[] = [
  { provider: "google", label: "Google", testId: "login-google", icon: <GoogleGlyph /> },
  { provider: "github", label: "GitHub", testId: "login-github", icon: <GitHubGlyph width={16} height={16} /> },
  { provider: "x", label: "X", testId: "login-x", icon: <XGlyph /> },
];

function OAuthButtons({
  pending,
  onOAuth,
  stretch,
}: {
  pending: AuthCardProps["pending"];
  onOAuth?: AuthCardProps["onOAuth"];
  stretch: boolean;
}) {
  return (
    <>
      {OAUTH.map((item) => (
        <button
          key={item.provider}
          type="button"
          className="acct-oauth"
          style={stretch ? { flex: 1, width: "auto" } : undefined}
          disabled={pending !== null && pending !== undefined}
          aria-label={item.label}
          title={item.label}
          data-testid={item.testId}
          onClick={() => onOAuth?.(item.provider)}
        >
          {item.icon}
        </button>
      ))}
    </>
  );
}

export function AuthCard({
  layout,
  mode = "signin",
  productName = "digiquant",
  mark,
  email = "",
  password = "",
  onEmailChange,
  onPasswordChange,
  onSubmit,
  onOAuth,
  onForgotPassword,
  pending = null,
  error = null,
  info = null,
  switchHref,
  idPrefix,
}: AuthCardProps) {
  const signUp = mode === "signup";
  const prefix = idPrefix ?? `acct-${layout}-${mode}`;
  const emailId = `${prefix}-email`;
  const passwordId = `${prefix}-password`;
  const score = passwordStrength(password);
  const href = switchHref ?? (signUp ? "/login/" : "/signup/");
  const busy = pending !== null;

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    onSubmit?.(event);
  }

  const fields = (
    <>
      <div className="acct-auth-field">
        <label className="acct-auth-label" htmlFor={emailId}>
          Email
        </label>
        <input
          className={error ? "acct-auth-input acct-auth-input-error" : "acct-auth-input"}
          id={emailId}
          name="email"
          type="email"
          autoComplete="username"
          value={email}
          onChange={(event) => onEmailChange?.(event.target.value)}
          placeholder="you@desk.tld"
        />
      </div>
      <div className="acct-auth-field">
        <label className="acct-auth-label" htmlFor={passwordId}>
          Password
        </label>
        <input
          className={error ? "acct-auth-input acct-auth-input-error" : "acct-auth-input"}
          id={passwordId}
          name="password"
          type="password"
          autoComplete={signUp ? "new-password" : "current-password"}
          value={password}
          onChange={(event) => onPasswordChange?.(event.target.value)}
          placeholder={signUp ? "8+ chars, mixed case, a digit" : "••••••••••"}
          aria-describedby={layout === "desk" && signUp ? `${prefix}-strength` : undefined}
        />
        {layout === "desk" && signUp ? (
          <div className="acct-auth-strength">
            <div className="acct-auth-strength-track" aria-hidden="true">
              {[0, 1, 2, 3].map((index) => (
                <span
                  key={index}
                  className="acct-auth-strength-seg"
                  style={index < score ? { background: STRENGTH_COLORS[score] } : undefined}
                />
              ))}
            </div>
            <span className="acct-auth-strength-word" id={`${prefix}-strength`} role="status">
              {STRENGTH_WORDS[score] || "—"}
            </span>
          </div>
        ) : null}
      </div>
    </>
  );

  const submitLabel = pending === "email" ? (signUp ? "Creating…" : "Signing in…") : signUp ? "Sign up" : "Sign in";
  const markNode = mark ?? <DigiquantMark size={28} />;
  const brand =
    layout === "compact" ? (
      <div className="acct-auth-brand">
        <div className="acct-auth-mark">{markNode}</div>
        <span className="acct-auth-wordmark">{productName}</span>
      </div>
    ) : (
      <div className="acct-auth-mark">{markNode}</div>
    );

  let body: ReactNode;
  switch (layout) {
    case "compact":
      body = (
        <>
          {fields}
          <div className="acct-auth-actions">
            <OAuthButtons pending={pending} onOAuth={onOAuth} stretch={false} />
            <button
              type="submit"
              className="btn-primary acct-auth-submit"
              disabled={busy}
              data-testid="login-email-submit"
            >
              {submitLabel}
            </button>
          </div>
        </>
      );
      break;
    case "icons-first":
      body = (
        <>
          <div className="acct-auth-oauth-row">
            <OAuthButtons pending={pending} onOAuth={onOAuth} stretch />
          </div>
          <div className="acct-auth-divider">
            <span>or email</span>
          </div>
          {fields}
          <button
            type="submit"
            className="btn-primary acct-auth-submit-block"
            disabled={busy}
            data-testid="login-email-submit"
          >
            {submitLabel}
          </button>
        </>
      );
      break;
    case "desk":
      body = (
        <>
          <p className="acct-auth-kicker">
            {productName}{" "}
            <span className="text-ink-mute">{signUp ? "· create account" : "· sign in"}</span>
          </p>
          <p className="acct-auth-copy">
            {signUp
              ? "Google, GitHub, or X to start. Email if you would rather keep a password."
              : "Email and a password, or a provider."}
          </p>
          {fields}
          <div className="acct-auth-actions">
            <OAuthButtons pending={pending} onOAuth={onOAuth} stretch={false} />
            <button
              type="submit"
              className="btn-primary acct-auth-submit"
              disabled={busy}
              data-testid="login-email-submit"
            >
              {submitLabel}
            </button>
          </div>
          {!signUp ? (
            <button type="button" className="acct-auth-forgot" onClick={onForgotPassword}>
              Forgot password?
            </button>
          ) : null}
        </>
      );
      break;
    default: {
      const _never: never = layout;
      body = _never;
    }
  }

  return (
    <form className="acct-auth" data-layout={layout} data-mode={mode} onSubmit={handleSubmit} noValidate>
      {brand}
      {body}
      <p className="acct-auth-switch">
        {signUp ? <a href={href}>Sign in</a> : <a href={href}>Create an account</a>}
      </p>
      {error ? (
        <p className="acct-auth-error" role="alert">
          {error}
        </p>
      ) : null}
      {info ? (
        <p className="acct-auth-info" role="status">
          {info}
        </p>
      ) : null}
    </form>
  );
}
