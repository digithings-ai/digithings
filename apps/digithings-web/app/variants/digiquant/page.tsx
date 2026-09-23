import type { Metadata } from "next";
import { DigiquantVariants } from "@/components/landing/DigiquantVariants";
import { GROUPED_LABEL } from "@/components/landing/label";

/**
 * A throwaway comparison page for the digiquant band, not part of the site.
 *
 * The owner asked for the section to be reworked into "kind of like an
 * advertisement page of digiquant's main services" and, explicitly, to "make a
 * separate page and give you a few variations of what you would put on this
 * digiquant section". This is that page: three compositions of the same band,
 * stacked, so one can be picked and folded into `QuantSection.tsx`.
 *
 * Deliberately not linked from the nav or the footer, and marked noindex — it
 * exists to be looked at once, then deleted. The nav is left off so the three
 * bands are the only thing on screen and can be compared without scrolling past
 * chrome.
 */

export const metadata: Metadata = {
  title: "digiquant band — variations",
  robots: { index: false, follow: false },
};

export default function DigiquantVariantsPage() {
  return (
    <main className="flex flex-col">
      <div className="px-[var(--page-pad)] pb-[1rem] pt-[3rem]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem]">
          <span className={GROUPED_LABEL}>internal · not linked · not indexed</span>
          <h1 className="m-0 font-mono text-[clamp(1.6rem,3.4vw,2.4rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            The digiquant band, three ways
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            Same content, three different leads: strategies, performance, pipeline. Pick one and it
            replaces the band on the landing page; the other two and this page go away.
          </p>
        </div>
      </div>
      <DigiquantVariants />
    </main>
  );
}
