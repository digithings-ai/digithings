"use client";

import { useState, type FormEvent } from "react";

/**
 * Sign-up — the account-creation card, same grammar as sign-in with one addition:
 * a live password-strength meter of four hairline segments scored from length and
 * character classes, climbing danger → warn → up as you type. An interactive
 * display template.
 */

const STRENGTH_WORDS = ["", "weak", "fair", "good", "strong"] as const;
const STRENGTH_COLORS = ["", "var(--down)", "var(--warn)", "var(--warn)", "var(--up)"] as const;

function passwordStrength(password: string): number {
  if (password.length === 0) return 0;
  let score = 1;
  if (password.length >= 8) score += 1;
  if (/[a-z]/.test(password) && /[A-Z]/.test(password)) score += 1;
  if (/\d/.test(password) || /[^a-zA-Z0-9]/.test(password)) score += 1;
  return Math.min(score, 4);
}

function preventSubmit(event: FormEvent<HTMLFormElement>) {
  event.preventDefault();
}

export function SignupCard() {
  const [password, setPassword] = useState("");
  const score = passwordStrength(password);

  return (
    <section className="section-block">
      <p className="kicker">{"// sign-up"}</p>
      <h2 className="title">From zero to keys in one card.</h2>
      <p className="section-copy">
        Same card grammar as sign-in — the only addition is a live strength meter: four hairline
        segments scored from length and character classes, climbing danger → warn → up. Type in the
        password field to see it move.
      </p>
      <p className="mt-4">
        <span className="inline-block whitespace-nowrap rounded-full border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          example data · not live
        </span>
      </p>

      <div className="mt-4 grid grid-cols-[repeat(auto-fit,minmax(280px,380px))] items-start gap-[1.2rem]">
        <form
          className="w-full max-w-[380px] rounded-[12px] border border-hair bg-surface p-[1.2rem]"
          onSubmit={preventSubmit}
          noValidate
        >
          <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
            digithings <span className="text-ink-mute">· create account</span>
          </p>
          <div className="acct-field">
            <label
              className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
              htmlFor="signup-email"
            >
              Email
            </label>
            <input
              className="acct-input"
              id="signup-email"
              name="email"
              type="email"
              placeholder="you@desk.tld"
              autoComplete="off"
            />
          </div>
          <div className="acct-field">
            <label
              className="block font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
              htmlFor="signup-password"
            >
              Password
            </label>
            <input
              className="acct-input"
              id="signup-password"
              name="password"
              type="password"
              placeholder="12+ chars, mixed case, a digit"
              autoComplete="off"
              value={password}
              onChange={(event) => setPassword(event.target.value)}
              aria-describedby="signup-strength"
            />
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
                id="signup-strength"
                role="status"
              >
                {STRENGTH_WORDS[score] || "—"}
              </span>
            </div>
          </div>
          <label className="acct-terms" htmlFor="signup-terms">
            <input id="signup-terms" name="terms" type="checkbox" />
            <span>I accept the terms — and the audit log that comes with them.</span>
          </label>
          <button type="submit" className="btn-primary acct-btn-block">
            Create account
          </button>
        </form>
      </div>
    </section>
  );
}
