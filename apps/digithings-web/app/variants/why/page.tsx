import type { Metadata } from "next";
import { GROUPED_LABEL } from "@/components/landing/label";
import { WhyStack } from "@/components/landing/WhyStack";

export const metadata: Metadata = {
  title: "#why — the same system, rented and owned",
  robots: { index: false, follow: false },
};

/**
 * The why-section composition, on a throwaway page (#4429 round 10).
 *
 * The owner asked for the industry convention rather than the simple node graph
 * round 9c shipped — "the specific graph that you typically build when you're
 * designing a system or an architecture" — which is the C4 container view. So
 * this page is now: two container diagrams, the capability comparison, and the
 * cost model with its assumptions stated. Nothing here is linked or indexed.
 */
export default function WhyVariantsPage() {
  return (
    <main className="flex flex-col">
      <div className="px-[var(--page-pad)] pb-[1rem] pt-[3rem]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem]">
          <span className={GROUPED_LABEL}>internal · not linked · not indexed</span>
          <h1 className="m-0 font-mono text-[clamp(1.6rem,3.4vw,2.4rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            Why digithings — the same system, rented and owned
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            Two container diagrams of the same AI stack — the drawing an engineer makes when
            designing a system: a box per service, a line per call, a rectangle around what you own.
            The first is the conventional arrangement, where everything below your application is a
            rented product inside one vendor boundary. The second is the same shape built from the
            digithings modules. Then the same nine questions asked of both, and a cost model whose
            every figure is a published list rate rather than a quote. No vendor is named.
          </p>
        </div>
      </div>

      <WhyStack />
    </main>
  );
}
