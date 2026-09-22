"use client";

import type { FormEvent } from "react";

import { Button, Input, Label, Separator } from "@digithings/ui/ui";

/**
 * Login — the sign-in card. Three states: oauth first, email default, and
 * error. OAuth first is Google filled, GitHub outline, then email under a
 * hairline. An interactive display template.
 *
 * Wave 1 / wave 3: fields are the stock kit — Input/Label/Separator/Button
 * from `@digithings/ui/ui`; the mono micro-caps label type, the block-button
 * width/margins, and the error tone are the reference's call-site grammar.
 * The quiet "Forgot password?" control is the kit Button `variant="outline"`
 * (wave-2 variant map: `.btn-quiet → outline`). The old
 * input/field/divider/error/forgot/block-button dress is gone; the error
 * state rides the input's own `aria-invalid` treatment.
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
                htmlFor="login-oauth-email"
              >
                Email
              </Label>
              <Input
                id="login-oauth-email"
                name="email"
                type="email"
                placeholder="you@desk.tld"
                autoComplete="off"
              />
            </div>
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="login-oauth-password"
              >
                Password
              </Label>
              <Input
                id="login-oauth-password"
                name="password"
                type="password"
                placeholder="••••••••••"
                autoComplete="off"
              />
            </div>
            <Button type="submit" variant="outline" className="mt-[1.1rem] w-full">
              Sign in with email
            </Button>
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
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="login-email"
              >
                Email
              </Label>
              <Input
                id="login-email"
                name="email"
                type="email"
                placeholder="you@desk.tld"
                autoComplete="off"
              />
            </div>
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="login-password"
              >
                Password
              </Label>
              <Input
                id="login-password"
                name="password"
                type="password"
                placeholder="••••••••••"
                autoComplete="off"
              />
            </div>
            <Button type="submit" className="mt-[1.1rem] w-full">
              Sign in
            </Button>
            <div className="my-4 flex items-center gap-[0.7rem] font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
              <Separator className="h-px flex-1" />
              <span>or</span>
              <Separator className="h-px flex-1" />
            </div>
            <Button type="button" variant="outline" className="mt-[1.1rem] w-full">
              Continue with SSO
            </Button>
            <Button type="button" variant="outline" className="mt-2 w-full">
              Forgot password?
            </Button>
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
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="login-error-email"
              >
                Email
              </Label>
              <Input
                id="login-error-email"
                name="email"
                type="email"
                defaultValue="cstefan@desk.tld"
                autoComplete="off"
                aria-invalid="true"
                aria-describedby="login-error-note"
              />
            </div>
            <div className="mt-[0.85rem] flex flex-col gap-[0.35rem]">
              <Label
                className="font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute"
                htmlFor="login-error-password"
              >
                Password
              </Label>
              <Input
                id="login-error-password"
                name="password"
                type="password"
                defaultValue="hunter2"
                autoComplete="off"
                aria-invalid="true"
                aria-describedby="login-error-note"
              />
              <p className="font-mono text-[0.68rem] text-danger" id="login-error-note" role="alert">
                invalid credentials — 2 attempts remaining
              </p>
            </div>
            <Button type="submit" className="mt-[1.1rem] w-full">
              Sign in
            </Button>
            <div className="my-4 flex items-center gap-[0.7rem] font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
              <Separator className="h-px flex-1" />
              <span>or</span>
              <Separator className="h-px flex-1" />
            </div>
            <Button type="button" variant="outline" className="mt-[1.1rem] w-full">
              Continue with SSO
            </Button>
            <Button type="button" variant="outline" className="mt-2 w-full">
              Forgot password?
            </Button>
          </form>
        </div>
      </div>
    </section>
  );
}
