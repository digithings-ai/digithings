import type { Metadata } from "next";
import { GROUPED_LABEL } from "@/components/landing/label";
import { WhyStack } from "@/components/landing/WhyStack";
import { LEDGER } from "@/lib/whyStack";

export const metadata: Metadata = {
  title: "#why — the same system, rented and owned",
  robots: { index: false, follow: false },
};

/**
 * The why-section composition, on a throwaway page (#4429 round 9c).
 *
 * One treatment, deliberately: the push. Each half is an architecture diagram —
 * nodes and connectors, the drawing an engineer makes when designing a system —
 * and they share one frame so the comparison is immediate. The conventional side
 * names no vendor; the owned side names the modules, because that is the product.
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
            The same architecture drawn twice, node for node: on the left the conventional
            off-the-shelf stack, where one vendor boundary closes around the model, the index, the
            database, the queue, the telemetry, the cache and the cloud; then the push into the same
            frame built from the digithings modules, where every box is a process you run. No vendor
            is named, and no figure on this page is a quote.
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
