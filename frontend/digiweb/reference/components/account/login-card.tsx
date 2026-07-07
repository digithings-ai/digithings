"use client";

import type { FormEvent } from "react";

function preventSubmit(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
}

export function LoginCard() {
  return (
    <section className="section-block">
      <p className="kicker">{"// login"}</p>
      <h2 className="title">Prove it&apos;s you, without ceremony.</h2>
      <p className="section-copy">
        One card, one filled CTA, SSO one hairline below. The error state swaps the border to the
        danger token and says exactly what happened — no toast, no shake, no lockout riddle.
      </p>
      <p className="acct-badge-row">
        <span className="acct-badge">example data · not live</span>
      </p>

      <div className="acct-auth-grid">
        <div>
          <p className="acct-variant">{"// default"}</p>
          <form className="acct-card" onSubmit={preventSubmit} noValidate>
            <p className="acct-card-mark">
              digithings <span>· sign in</span>
            </p>
            <div className="acct-field">
              <label className="acct-label" htmlFor="login-email">
                Email
              </label>
              <input
                className="acct-input"
                id="login-email"
                name="email"
                type="email"
                placeholder="you@desk.tld"
                autoComplete="off"
              />
            </div>
            <div className="acct-field">
              <label className="acct-label" htmlFor="login-password">
                Password
              </label>
              <input
                className="acct-input"
                id="login-password"
                name="password"
                type="password"
                placeholder="••••••••••"
                autoComplete="off"
              />
            </div>
            <button type="submit" className="btn-primary acct-btn-block">
              Sign in
            </button>
            <div className="acct-divider">
              <span>or</span>
            </div>
            <button type="button" className="btn-ghost acct-btn-block">
              Continue with SSO
            </button>
            <button type="button" className="btn-quiet acct-forgot">
              Forgot password?
            </button>
          </form>
        </div>

        <div>
          <p className="acct-variant">{"// error state"}</p>
          <form className="acct-card" onSubmit={preventSubmit} noValidate>
            <p className="acct-card-mark">
              digithings <span>· sign in</span>
            </p>
            <div className="acct-field">
              <label className="acct-label" htmlFor="login-error-email">
                Email
              </label>
              <input
                className="acct-input acct-input-error"
                id="login-error-email"
                name="email"
                type="email"
                defaultValue="cstefan@desk.tld"
                autoComplete="off"
                aria-invalid="true"
                aria-describedby="login-error-note"
              />
            </div>
            <div className="acct-field">
              <label className="acct-label" htmlFor="login-error-password">
                Password
              </label>
              <input
                className="acct-input acct-input-error"
                id="login-error-password"
                name="password"
                type="password"
                defaultValue="hunter2"
                autoComplete="off"
                aria-invalid="true"
                aria-describedby="login-error-note"
              />
              <p className="acct-error" id="login-error-note" role="alert">
                invalid credentials — 2 attempts remaining
              </p>
            </div>
            <button type="submit" className="btn-primary acct-btn-block">
              Sign in
            </button>
            <div className="acct-divider">
              <span>or</span>
            </div>
            <button type="button" className="btn-ghost acct-btn-block">
              Continue with SSO
            </button>
            <button type="button" className="btn-quiet acct-forgot">
              Forgot password?
            </button>
          </form>
        </div>
      </div>
    </section>
  );
}
