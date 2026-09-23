import type { Metadata } from "next";
import { WhyVariants } from "@/components/landing/WhyVariants";
import { GROUPED_LABEL } from "@/components/landing/label";

/**
 * A throwaway comparison page for the `#why` section, not part of the site.
 *
 * The owner asked for the section to be refined — "the arrow should appear on the
 * line itself, kind of breaking the line apart … we kind of show the managed
 * platform first and then we show all the digithings improvements of how it kind
 * of changes the managed platform and turns it into a fully modular, customizable
 * infrastructure that you actually own" — and to "design a few versions of this
 * and … host it on a local host app".
 *
 * This is that page: four compositions of the same seven-layer argument, plus the
 * benefit ledger, stacked so one can be picked and folded into `Argument.tsx`.
 * Deliberately not linked from the nav or the footer, and marked noindex.
 */

export const metadata: Metadata = {
  title: "#why — variations",
  robots: { index: false, follow: false },
};

export default function WhyVariantsPage() {
  return (
    <main className="flex flex-col">
      <div className="px-[var(--page-pad)] pb-[1rem] pt-[3rem]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem]">
          <span className={GROUPED_LABEL}>internal · not linked · not indexed</span>
          <h1 className="m-0 font-mono text-[clamp(1.6rem,3.4vw,2.4rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            Why digithings, four ways
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            The same seven layers, four arrangements. 01 is the comparison we ship today with the
            arrow sitting on the rule; 02–04 animate the same stack coming apart. Pick one and it
            replaces the band; the other three and this page go away.
          </p>
        </div>
      </div>
      <WhyVariants />
    </main>
  );
}
