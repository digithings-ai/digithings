/** Shared chrome for the three legal skeletons (/legal/terms, /legal/privacy,
 *  /legal/disclaimer).
 *
 *  >>> THESE PAGES NEED REAL COUNSEL BEFORE THEY GO LIVE. <<<
 *
 *  They are deliberately skeletons: the section headings a lawyer would fill,
 *  plus one neutral sentence of scope each. No binding terms, no warranty
 *  language, no liability cap, no limitation-of-liability clause, no governing
 *  law, no privacy representations that could read as final. That restraint is
 *  not laziness — this repository ships digiquant, which touches backtesting and
 *  (behind a human gate) trade execution, so a disclaimer that is merely
 *  plausible is worse than one that is visibly absent. A wrong warranty
 *  disclaimer or an under-specified financial disclaimer is a liability, not a
 *  copy defect.
 *
 *  Note that the repository's own MIT LICENSE already carries the software
 *  warranty disclaimer for the code. These pages are about the *website and the
 *  services*, which the licence does not cover, and the two must not be
 *  conflated by whoever drafts them.
 *
 *  Every page renders <DraftBanner /> above its content so no visitor can
 *  mistake the skeleton for a policy in force. Remove the banner only when real
 *  reviewed text replaces the placeholders.
 *
 *  Built from existing canon classes (.section, .wrap, .kicker, .hero-title)
 *  and token-backed utilities only — no new CSS families.
 */
import type { ReactNode } from "react";

/** The visible not-a-policy notice. Warn-toned, hairline-framed, and given
 *  role="note" with an aria-label so assistive tech announces it as an aside
 *  rather than as body copy. */
export function DraftBanner() {
  return (
    <div
      role="note"
      aria-label="Draft notice"
      className="rounded-[12px] border border-warn bg-surface p-[1.1rem_1.2rem]"
    >
      <span className="block font-mono text-[0.68rem] uppercase tracking-[0.16em] text-warn">
        Draft — not in force
      </span>
      <p className="mt-[0.5rem] max-w-[70ch] text-[0.9rem] leading-[1.65] text-ink-soft">
        This page is an unreviewed outline, published so the structure is visible while it is being
        written. It is <strong className="font-medium text-ink">not legal advice</strong>, it is not
        a binding agreement, and it does not yet state any policy that DigiThings operates under. It
        is pending review by qualified counsel and will change. Do not rely on anything below.
      </p>
      <p className="mt-[0.6rem] max-w-[70ch] text-[0.9rem] leading-[1.65] text-ink-soft">
        If you need a definitive answer before this is finished, ask us directly and we will answer
        in writing.
      </p>
    </div>
  );
}

/** One outline section: the heading a lawyer would fill, plus a single neutral
 *  sentence naming what belongs there. `note` never asserts a term — it
 *  describes the subject matter of the missing clause. */
export type DraftSection = { heading: string; note: string };

export function DraftOutline({ sections }: { sections: DraftSection[] }) {
  return (
    <ol className="m-0 grid list-none gap-0 p-0">
      {sections.map((s, i) => (
        <li
          key={s.heading}
          className="grid gap-[0.3rem] border-t border-hair py-[1.1rem] last:border-b sm:grid-cols-[3rem_1fr] sm:gap-[1.2rem]"
        >
          <span className="font-mono text-[0.8rem] text-ink-mute">
            {String(i + 1).padStart(2, "0")}
          </span>
          <span className="grid gap-[0.3rem]">
            <span className="font-mono text-[0.95rem] text-ink">{s.heading}</span>
            <span className="text-[0.9rem] leading-[1.65] text-ink-soft">{s.note}</span>
            <span className="font-mono text-[0.72rem] uppercase tracking-[0.12em] text-ink-mute">
              to be drafted
            </span>
          </span>
        </li>
      ))}
    </ol>
  );
}

/** The closing block every legal skeleton shares: who to ask in the meantime,
 *  and a pointer to the licence that *does* apply to the code today. */
export function DraftFooterNote({ children }: { children: ReactNode }) {
  return (
    <p className="mt-[1.8rem] max-w-[68ch] text-[0.92rem] leading-[1.7] text-ink-soft">{children}</p>
  );
}
