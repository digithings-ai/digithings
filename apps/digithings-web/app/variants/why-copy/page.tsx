import type { Metadata } from "next";
import { WhyCopyVariants } from "@/components/landing/WhyCopyVariants";
import { GROUPED_LABEL } from "@/components/landing/label";

/**
 * A throwaway comparison page for the why band, not part of the site.
 *
 * The owner asked for a few fully built-out versions of the section to look
 * at and pick from — then for completely different variants: different text,
 * different diagrams, different display. So this page is three different
 * arguments with three different drawings: A (monolith vs exploded walk),
 * B (cumulative adoption ladder), C (invoice ledger duel). The winner's
 * argument migrates into `WhyStack.tsx` + `lib/whyStack.ts`; the rest goes
 * away.
 *
 * Deliberately not linked from the nav or the footer, and marked noindex.
 */

export const metadata: Metadata = {
  title: "why band — variations v2",
  robots: { index: false, follow: false },
};

export default function WhyCopyVariantsPage() {
  return (
    <main className="flex flex-col">
      <div className="px-[var(--page-pad)] pb-[1rem] pt-[3rem]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem]">
          <span className={GROUPED_LABEL}>internal · not linked · not indexed</span>
          <h1 className="m-0 font-mono text-[clamp(1.6rem,3.4vw,2.4rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            The why band, three different ways
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            Three arguments, three drawings: a monolith walked against the
            module build, an adoption ladder that grows in place, an invoice
            duel with no diagrams at all. Scroll each, pick one.
          </p>
        </div>
      </div>
      <WhyCopyVariants />
    </main>
  );
}
