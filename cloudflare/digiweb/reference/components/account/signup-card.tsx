"use client";

import { useState, type FormEvent } from "react";

import { Checkbox } from "@digithings/web";
import { Button, Input, Label, Separator } from "@digithings/web/ui";

/**
 * Sign-up — the account-creation card, same grammar as sign-in with a live
 * password-strength meter and OAuth fallbacks (Google / GitHub) under a hairline.
 *
 * Wave 1: fields are the stock kit — Input/Label/Separator/Button from
 * `@digithings/web/ui`; the terms row pairs a `@digithings/web` controls-layer
 * Checkbox with a Label (the form-fields grammar). The strength meter keeps
 * its four-segment grid on call-site utilities; the terms/checkbox dress and
 * the `.acct-*` field dress are gone.
 */

const STRENGTH_WORDS = ["", "weak", "fair", "good", "strong"] as const;
const STRENGTH_COLORS = ["", "var(--danger)", "var(--accent)", "var(--accent)", "var(--ink)"] as const;

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
              digiquant <span className="text-ink-mute">· create account</span>
            </p>
            <p className="mt-2 font-display text-[1.45rem] font-normal leading-[1.15] tracking-[-0.02em] text-ink">
              From zero to the desk.
            </p>
            <p className="mt-2 text-[0.88rem] leading-[1.45] text-ink-soft">
              Google or GitHub to start. Email if you would rather keep a password.
            </p>
            <Button type="button" className="mt-[1.1rem] w-full">
              Continue with Google
            </Button>
            <Button type="button" variant="outline" className="mt-[1.1rem] w-full">
              Continue with GitHub
            </Button>
            <div className="my-4 flex items-center gap-[0.7rem] font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
              <Separator className="h-px flex-1" />
              <span>or email</span>
              <Separator className="h-px flex-1" />
            </div>
            <div className="flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="signup-oauth-email"
              >
                Email
              </Label>
              <Input
                id="signup-oauth-email"
                name="email"
                type="email"
                placeholder="you@desk.tld"
                autoComplete="off"
              />
            </div>
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="signup-oauth-password"
              >
                Password
              </Label>
              <Input
                id="signup-oauth-password"
                name="password"
                type="password"
                placeholder="8+ chars, mixed case, a digit"
                autoComplete="off"
              />
            </div>
            <Button type="submit" variant="outline" className="mt-[1.1rem] w-full">
              Create account with email
            </Button>
          </form>
        </div>

        <div>
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {"// email first"}
          </p>
          <form
            className="w-full max-w-[380px] rounded-none border border-hair bg-surface p-[1.2rem]"
            onSubmit={preventSubmit}
            noValidate
          >
            <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
              digithings <span className="text-ink-mute">· create account</span>
            </p>
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="signup-email"
              >
                Email
              </Label>
              <Input
                id="signup-email"
                name="email"
                type="email"
                placeholder="you@desk.tld"
                autoComplete="off"
              />
            </div>
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="signup-password"
              >
                Password
              </Label>
              <Input
                id="signup-password"
                name="password"
                type="password"
                placeholder="8+ chars, mixed case, a digit"
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
                      className="h-[3px] bg-[color-mix(in_srgb,var(--ink-mute)_22%,transparent)] transition-[background] duration-[250ms] ease-[var(--ease)]"
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
            <Label
              className="mt-4 flex cursor-pointer items-start gap-2 font-mono text-[0.68rem] leading-[1.5] text-ink-soft"
              htmlFor="signup-terms"
            >
              <Checkbox className="mt-[2px]" id="signup-terms" name="terms" />
              <span>I accept the terms — and the audit log that comes with them.</span>
            </Label>
            <Button type="submit" className="mt-[1.1rem] w-full">
              Create account
            </Button>
            <div className="my-4 flex items-center gap-[0.7rem] font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
              <Separator className="h-px flex-1" />
              <span>or</span>
              <Separator className="h-px flex-1" />
            </div>
            <Button type="button" variant="outline" className="mt-[1.1rem] w-full">
              Continue with Google
            </Button>
            <Button type="button" variant="outline" className="mt-[1.1rem] w-full">
              Continue with GitHub
            </Button>
          </form>
        </div>
      </div>
    </section>
  );
}
