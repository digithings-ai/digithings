"use client";

import { AuthCard, type AuthCardLayout } from "@digithings/web";

const LAYOUTS: AuthCardLayout[] = ["compact", "icons-first", "desk"];

/**
 * Auth cards — three layouts of AuthCard from @digithings/web: compact,
 * icons-first, and desk. Sign-in and create-account share a card. Display
 * templates — submit is a no-op.
 */
export function AuthCardProposals() {
  return (
    <section className="section-block" data-testid="auth-cards">
      <p className="kicker">{"// sign-in cards"}</p>
      <h2 className="title">Three layouts, one card.</h2>
      <p className="section-copy">
        <code>AuthCard</code> from <code>@digithings/web</code>. Compact, icons-first, and desk
        share email, password, and Google / GitHub / X. Sign-in and create-account sit on the
        same form.
      </p>
      <p className="mt-4">
        <span className="inline-block whitespace-nowrap rounded-none border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          example data · not live
        </span>
      </p>

      {LAYOUTS.map((id) => (
        <div key={id} className="mt-8" data-layout={id}>
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {`// ${id}`}
          </p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,380px))] items-start gap-[1.2rem]">
            <div id={`auth-${id}-signin`}>
              <AuthCard
                layout={id}
                mode="signin"
                idPrefix={`acct-${id}-in`}
                switchHref={`#auth-${id}-signup`}
              />
            </div>
            <div id={`auth-${id}-signup`}>
              <AuthCard
                layout={id}
                mode="signup"
                idPrefix={`acct-${id}-up`}
                switchHref={`#auth-${id}-signin`}
              />
            </div>
          </div>
        </div>
      ))}
    </section>
  );
}
