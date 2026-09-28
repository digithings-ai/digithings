import type { Metadata } from "next";
import { AppFirstSection } from "@/components/landing/AppFirstSection";
import { WhyCopyVariants } from "@/components/landing/WhyCopyVariants";
import { GROUPED_LABEL } from "@/components/landing/label";

/**
 * A throwaway comparison page for the why band, not part of the site.
 *
 * Leads with the single app-first variant (three apps, clickable boxes,
 * live invoice) — the consolidation target. The older takes (Study D,
 * Study E, A/B/C) stay stacked below until the single variant wins, then
 * everything else and this page go away.
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
            The why band, app-first
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            One variant: pick an app, configure either stack by clicking its boxes,
            watch the walk and the invoice move together. Older studies stay stacked
            below until this one wins.
          </p>
        </div>
      </div>
      <AppFirstSection />
      <WhyCopyVariants />
    </main>
  );
}
