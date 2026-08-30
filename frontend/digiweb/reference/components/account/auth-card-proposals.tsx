"use client";

import { AuthCard, type AuthCardLayout } from "@digithings/web";

const LAYOUTS: { id: AuthCardLayout; letter: string; note: string }[] = [
  { id: "compact", letter: "A", note: "product card" },
  { id: "icons-first", letter: "B", note: "catalog" },
  { id: "desk", letter: "C", note: "catalog" },
];

/**
 * Auth cards — compact is the product login grammar (mark + digiquant wordmark);
 * icons-first and desk stay as catalog layouts. Sign-in and create-account share
 * a card. Display templates — submit is a no-op.
 */
export function AuthCardProposals() {
  return (
    <section className="section-block" data-testid="auth-cards">
      <p className="kicker">{"// sign-in cards"}</p>
      <h2 className="title">Compact row, product card.</h2>
      <p className="section-copy">
        <code>AuthCard</code> from <code>@digithings/web</code>. Compact (A) is the product
        login card: tool mark + <code>digiquant</code> wordmark, then email, password, and
        one row of Google / GitHub / X plus Sign in / Sign up. Icons-first and desk remain
        as catalog layouts. Provider id for X is <code>twitter</code>; the visible label is X.
      </p>
      <p className="mt-4">
        <span className="inline-block whitespace-nowrap rounded-none border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          example data · not live
        </span>
      </p>

      {LAYOUTS.map((item) => (
        <div
          key={item.id}
          className="mt-8"
          data-layout={item.id}
          data-proposal={item.letter}
          data-selected={item.id === "compact" ? "true" : "false"}
        >
          <p className="mb-2 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
            {`// ${item.id} · ${item.note}`}
          </p>
          <div className="grid grid-cols-[repeat(auto-fit,minmax(280px,380px))] items-start gap-[1.2rem]">
            <AuthCard layout={item.id} mode="signin" idPrefix={`acct-${item.id}-in`} />
            <AuthCard layout={item.id} mode="signup" idPrefix={`acct-${item.id}-up`} />
          </div>
        </div>
      ))}
    </section>
  );
}
