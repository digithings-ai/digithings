"use client";

import {
  AuthCard,
  type AuthCardLayout,
} from "@digithings/web";

const LAYOUTS: { id: AuthCardLayout; letter: string; title: string; blurb: string }[] = [
  {
    id: "compact",
    letter: "A",
    title: "Compact row",
    blurb: "Logo. Email. Password. Google / GitHub / X as small boxes beside Sign in.",
  },
  {
    id: "icons-first",
    letter: "B",
    title: "Icons first",
    blurb: "Logo. Provider boxes across the top. Hairline. Email, then a full-width Sign in.",
  },
  {
    id: "desk",
    letter: "C",
    title: "Desk card",
    blurb: "Logo plus product name. Short help. Strength meter on sign-up. Forgot password on sign-in.",
  },
];

/**
 * Side-by-side AuthCard layouts so the operator can pick one before the
 * dashboard imports it. Display templates — submit is a no-op.
 */
export function AuthCardProposals() {
  return (
    <section className="section-block" data-testid="auth-card-proposals">
      <p className="kicker">{"// auth proposals"}</p>
      <h2 className="title">Pick a sign-in grammar.</h2>
      <p className="section-copy">
        Three layouts of the same <code>AuthCard</code> from <code>@digithings/web</code>. Sign-in
        and create-account share a card. No olympus kicker. Reply A, B, or C.
      </p>
      <p className="mt-4">
        <span className="inline-block whitespace-nowrap rounded-none border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          example data · not live
        </span>
      </p>

      {LAYOUTS.map((item) => (
        <div key={item.id} className="mt-8" data-proposal={item.letter}>
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {`// ${item.letter} — ${item.title}`}
          </p>
          <p className="mb-4 max-w-[62ch] text-[0.88rem] leading-[1.45] text-ink-soft">{item.blurb}</p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,380px))] items-start gap-[1.2rem]">
            <AuthCard layout={item.id} mode="signin" idPrefix={`prop-${item.id}-in`} />
            <AuthCard layout={item.id} mode="signup" idPrefix={`prop-${item.id}-up`} />
          </div>
        </div>
      ))}
    </section>
  );
}
