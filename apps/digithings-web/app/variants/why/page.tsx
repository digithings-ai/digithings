import type { Metadata } from "next";
import { GROUPED_LABEL } from "@/components/landing/label";
import { WhyStack } from "@/components/landing/WhyStack";
import { LEDGER } from "@/lib/whyStack";

export const metadata: Metadata = {
  title: "#why — the trap, then the shoe that fits",
  robots: { index: false, follow: false },
};

/**
 * The why-section composition, on a throwaway page (#4429 round 9).
 *
 * Two treatments of the same composition — the same copy, the same two
 * diagrams, the same ten-step rail — differing only in how the stage swaps:
 *
 *   A  swipe — the rail slides across the stage and the visuals cross-fade in
 *      place. Closest to "we swipe that around and the text moves to the left".
 *   B  push — the rented stack leaves by the left edge while DigiThings pushes
 *      in from the right. Heavier, more like a page turn.
 *
 * Both carry the benefit ledger underneath, written as what structurally
 * changes: no figure appears anywhere on this page.
 */
export default function WhyVariantsPage() {
  return (
    <main className="flex flex-col">
      <div className="px-[var(--page-pad)] pb-[1rem] pt-[3rem]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem]">
          <span className={GROUPED_LABEL}>internal · not linked · not indexed</span>
          <h1 className="m-0 font-mono text-[clamp(1.6rem,3.4vw,2.4rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            Why digithings — the trap, then the shoe that fits
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            The rented stack laid out component by component with what each one bills on, then the
            swap into the same layers owned. Two treatments: A swipes the rail across the stage, B
            pushes the rented half off the left edge. No figure on this page is a quote, and no
            vendor is named.
          </p>
        </div>
      </div>

      <div className="px-[var(--page-pad)] pt-[1rem]">
        <div className="mx-auto max-w-[var(--frame-w)]">
          <p className={`m-0 mb-[0.8rem] ${GROUPED_LABEL}`}>treatment A · swipe</p>
        </div>
      </div>
      <WhyStack variant="swipe" />

      <div className="px-[var(--page-pad)] pt-[3rem]">
        <div className="mx-auto max-w-[var(--frame-w)]">
          <p className={`m-0 mb-[0.8rem] ${GROUPED_LABEL}`}>treatment B · push</p>
        </div>
      </div>
      <WhyStack variant="push" />

      <section className="px-[var(--page-pad)] py-[var(--page-step)]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[1.4rem]">
          <h2 className="m-0 font-mono text-[clamp(1.3rem,2.4vw,1.85rem)] font-medium leading-[1.2] tracking-[-0.02em] text-ink">
            What actually changes
          </h2>
          <ul className="why-ledger">
            {LEDGER.map((row) => (
              <li key={row.claim} className="why-ledger__row">
                <span className="why-ledger__claim">{row.claim}</span>
                <span className="why-ledger__because">{row.because}</span>
              </li>
            ))}
          </ul>
        </div>
      </section>
    </main>
  );
}
