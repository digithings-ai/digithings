"use client";

import type { FormEvent } from "react";

/**
 * Login — the sign-in card. Three states: oauth first, email default, and
 * error. OAuth first is Google filled, GitHub ghost, then email under a
 * hairline. An interactive display template.
 */

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
      <p className="mt-4">
        <span className="inline-block whitespace-nowrap rounded-none border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          example data · not live
        </span>
      </p>

      <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(280px,380px))] items-start gap-[1.2rem]">
        <div>
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {"// oauth first"}
          </p>
          <form
            className="w-full max-w-[380px] rounded-none border border-hair bg-surface p-[1.2rem]"
            onSubmit={preventSubmit}
            noValidate
          >
            <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
              digiquant <span className="text-ink-mute">· sign in</span>
            </p>
            <p className="mt-2 font-display text-[1.45rem] font-normal leading-[1.15] tracking-[-0.02em] text-ink">
              Open the desk.
            </p>
            <p className="mt-2 text-[0.88rem] leading-[1.45] text-ink-soft">
              Google or GitHub. Email if you already have a workspace password.
            </p>
            <button type="button" className="btn-primary acct-btn-block">
              Continue with Google
            </button>
            <button type="button" className="btn-ghost acct-btn-block">
              Continue with GitHub
            </button>
            <div className="acct-divider">
              <span>or email</span>
            </div>
            <div className="acct-field" style={{ marginTop: 0 }}>
              <label
                className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="login-oauth-email"
              >
                Email
              </label>
              <input
                className="acct-input"
                id="login-oauth-email"
                name="email"
                type="email"
                placeholder="you@desk.tld"
                autoComplete="off"
              />
            </div>
            <div className="acct-field">
              <label
                className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="login-oauth-password"
              >
                Password
              </label>
              <input
                className="acct-input"
                id="login-oauth-password"
                name="password"
                type="password"
                placeholder="••••••••••"
                autoComplete="off"
              />
            </div>
            <button type="submit" className="btn-ghost acct-btn-block">
              Sign in with email
            </button>
          </form>
        </div>

        <div>
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {"// default"}
          </p>
          <form
            className="w-full max-w-[380px] rounded-none border border-hair bg-surface p-[1.2rem]"
            onSubmit={preventSubmit}
            noValidate
          >
            <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
              digithings <span className="text-ink-mute">· sign in</span>
            </p>
            <div className="acct-field">
              <label className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute" htmlFor="login-email">
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
              <label className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute" htmlFor="login-password">
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
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {"// error state"}
          </p>
          <form
            className="w-full max-w-[380px] rounded-none border border-hair bg-surface p-[1.2rem]"
            onSubmit={preventSubmit}
            noValidate
          >
            <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
              digithings <span className="text-ink-mute">· sign in</span>
            </p>
            <div className="acct-field">
              <label className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute" htmlFor="login-error-email">
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
              <label className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute" htmlFor="login-error-password">
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
