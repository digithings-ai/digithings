"use client";

/**
 * Session — signed-in identity plus a quiet Sign out control. Same card grammar
 * as login: mark, mono meta, one hairline, one ghost action. Display template.
 */

export function SessionCard() {
  return (
    <section className="section-block">
      <p className="kicker">{"// session"}</p>
      <h2 className="title">You are in. Leaving is one line.</h2>
      <p className="section-copy">
        Signed-in chrome is a ledger line, not a profile billboard: email in mono, Sign out as a
        ghost control on the same hairline. No avatar stack, no toast on exit.
      </p>
      <p className="mt-4">
        <span className="inline-block whitespace-nowrap rounded-none border border-hair px-[0.6rem] py-[0.22rem] font-mono text-[0.6rem] uppercase tracking-[0.08em] text-ink-mute">
          example data · not live
        </span>
      </p>

      <div className="mt-4 w-full max-w-[380px] rounded-none border border-hair bg-surface p-[1.2rem]">
        <p className="font-mono text-[0.72rem] tracking-[0.02em] text-ink">
          olympus <span className="text-ink-mute">· signed in</span>
        </p>
        <p className="mt-3 font-mono text-[0.78rem] text-ink">you@desk.tld</p>
        <p className="mt-1 font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
          github · workspace free
        </p>
        <button type="button" className="btn-ghost acct-btn-block">
          Sign out
        </button>
      </div>
    </section>
  );
}
