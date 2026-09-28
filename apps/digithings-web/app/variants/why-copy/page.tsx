import type { Metadata } from "next";
import { AppFirstSection } from "@/components/landing/AppFirstSection";
import { GROUPED_LABEL } from "@/components/landing/label";

/**
 * A throwaway comparison page for the why band, not part of the site.
 *
 * A single variant: three apps with distinct architectures per app, one
 * consistent digithings shape, clickable boxes, and the invoice always
 * below reflecting the selected app. The older studies are gone (see git
 * history); when this wins it migrates to the live band and this page
 * goes away with it.
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
            Which stack runs your app?
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            Pick an app. Each draws its own architecture — click any box to reconfigure
            its layer, and the invoice below follows the selected app.
          </p>
        </div>
      </div>
      <AppFirstSection />
    </main>
  );
}
