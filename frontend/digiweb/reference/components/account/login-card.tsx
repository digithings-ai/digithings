"use client";

import type { FormEvent } from "react";

/**
 * Login — the sign-in card, shown twice: the default state and the error state
 * side by side. One card holds email, password, a filled CTA, and an SSO fallback
 * a hairline below; the error variant swaps input borders to the down token and
 * surfaces one plain-language note. An interactive display template.
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
        <span className="inline-block whitespace-nowrap rounded-full border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          example data · not live
        </span>
      </p>

      <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(280px,380px))] items-start gap-[1.2rem]">
        <div>
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {"// default"}
          </p>
          <form
            className="w-full max-w-[380px] rounded-[12px] border border-hair bg-surface p-[1.2rem]"
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
            className="w-full max-w-[380px] rounded-[12px] border border-hair bg-surface p-[1.2rem]"
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
