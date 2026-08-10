/**
 * Testimonial wall — a wall of pull-quotes with attribution (illustrative copy;
 * production uses real names per the voice doctrine). Consumes the shared
 * <TestimonialWall/> primitive from @digithings/web. Static display template.
 */
import { TestimonialWall, type TestimonialQuote } from "@digithings/web";

// Illustrative only — production copy uses real names/orgs (voice doctrine).
const QUOTES: TestimonialQuote[] = [
  {
    quote: "The tearsheet is the argument. We stopped screenshotting backtests and started sending re-runnable receipts.",
    name: "A. Reyes",
    role: "Systematic PM",
    org: "Northwind Capital",
  },
  {
    quote: "Self-hosted, BYOK, audit-on by default — it cleared compliance in a week instead of a quarter.",
    name: "J. Okafor",
    role: "Head of Risk",
    org: "Meridian Desk",
  },
  {
    quote: "atlas proposes, digiquant proves, hermes ships. The loop is the product.",
    name: "S. Vance",
    role: "Quant Lead",
    org: "Cedar Street",
  },
];

const ORGS = ["Northwind Capital", "Meridian Desk", "Cedar Street", "Halcyon", "Byres & Co"];

export function TestimonialWallReference() {
  return (
    <section className="section-block testimonial-wall">
      <p className="kicker">{"// social proof"}</p>
      <h2 className="title">Proof, honestly sourced.</h2>
      <p className="section-copy">
        The trust band: a pull-quote wall over a quiet org lockup. The voice rule is strict — real
        numbers and real orgs only, phrased as <code>{"{Org}"} × digiquant</code>, never invented.
        Everything here is illustrative, badged as such.
      </p>
      <p className="mt-[0.9rem] inline-block rounded-full border border-hair px-[0.6rem] py-[0.15rem] font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
        Example data · not live
      </p>

      <TestimonialWall
        className="mt-[1.2rem]"
        quotes={QUOTES}
        lockup="digiquant"
        orgs={ORGS}
        orgsLabel="trusted by"
        orgsAriaLabel="Illustrative organizations"
      />
    </section>
  );
}
