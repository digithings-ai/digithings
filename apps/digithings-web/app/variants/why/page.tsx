import type { Metadata } from "next";
import { GROUPED_LABEL } from "@/components/landing/label";
import { WhyStack } from "@/components/landing/WhyStack";
import { LEDGER } from "@/lib/whyStack";

export const metadata: Metadata = {
  title: "#why — the rented stack, then the same stack owned",
  robots: { index: false, follow: false },
};

/**
 * The why-section composition, on a throwaway page (#4429 round 9).
 *
 * One treatment, deliberately: the push. The owner picked it — "I prefer the
 * push variant" — and asked for the two architectures to share one grammar so
 * the comparison is immediate, with the conventional closed tools named on the
 * rented side, the surface limit made visible, and the bill accumulating by
 * count. No figure on this page is a quote.
 */
export default function WhyVariantsPage() {
  return (
    <main className="flex flex-col">
      <div className="px-[var(--page-pad)] pb-[1rem] pt-[3rem]">
        <div className="mx-auto flex max-w-[var(--frame-w)] flex-col gap-[0.5rem]">
          <span className={GROUPED_LABEL}>internal · not linked · not indexed</span>
          <h1 className="m-0 font-mono text-[clamp(1.6rem,3.4vw,2.4rem)] font-medium leading-[1.15] tracking-[-0.02em] text-ink">
            Why digithings — the rented stack, then the same stack owned
          </h1>
          <p className="m-0 max-w-[var(--measure-prose)] text-[0.9rem] leading-[1.7] text-ink-soft">
            The same five slots drawn twice: on the left what you rent through the conventional
            closed tools, with the cadence each one meters on and an invoice for every box; then the
            push into the same slots run on your own accounts. No figure on this page is a quote —
            each box says how it bills, never what it costs.
          </p>
        </div>
      </div>

      <WhyStack />

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
