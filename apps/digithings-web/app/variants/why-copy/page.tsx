import type { Metadata } from "next";
import { WhyCopyVariants } from "@/components/landing/WhyCopyVariants";
import { GROUPED_LABEL } from "@/components/landing/label";

/**
 * A throwaway comparison page for the why band, not part of the site.
 *
 * The owner asked for a few fully built-out versions of the section to look
 * at and pick from: three complete takes of the same band (A compose-it-
 * yourself, B never-locked-in, C no-middleman-meter), each a full guided
 * walk, stacked, so the pick is made on the experience. The winner migrates
 * into `WhyStack.tsx` + `lib/whyStack.ts`; the other two and this page go
 * away.
 *
 * Deliberately not linked from the nav or the footer, and marked noindex.
 */

export const metadata: Metadata = {
  title: "why band — variations",
  robots: { index: false, follow: false },
};

export default function WhyCopyVariantsPage() {
  return (
    <main className="flex flex-col">
      <div className="px-[var(--page-pad)] pb-[1rem] pt-[3rem]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem]">
          <span className={GROUPED_LABEL}>internal · not linked · not indexed</span>
          <h1 className="m-0 font-mono text-[clamp(1.6rem,3.4vw,2.4rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            The why band, three ways
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            Same eight module boxes, three different arguments: compose it yourself,
            never locked in, no middleman&apos;s meter. Scroll each walk, pick one,
            and it replaces the band on the landing page.
          </p>
        </div>
      </div>
      <WhyCopyVariants />
    </main>
  );
}
