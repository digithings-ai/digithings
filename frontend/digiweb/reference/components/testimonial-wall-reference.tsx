/**
 * Testimonial wall — a wall of pull-quotes with attribution (illustrative copy;
 * production uses real names per the voice doctrine). Static display template.
 */
type Quote = { quote: string; name: string; role: string; org: string };

// Illustrative only — production copy uses real names/orgs (voice doctrine).
const QUOTES: Quote[] = [
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
      {/* Token-backed Tailwind utilities via the @theme bridge: colour + font
          utilities emit var(--token) so they live-switch on data-theme / livery.
          Off-scale rem values stay as arbitrary utilities to preserve the design. */}
      <p className="mt-[0.9rem] inline-block rounded-full border border-hair px-[0.6rem] py-[0.15rem] font-mono text-[0.58rem] uppercase tracking-[0.08em] text-ink-mute">
        Example data · not live
      </p>

      <div className="mt-[1.2rem] grid grid-cols-3 gap-[0.9rem] max-[820px]:grid-cols-1">
        {QUOTES.map((q) => (
          <figure
            key={q.name}
            className="m-0 flex flex-col justify-between gap-[1.1rem] rounded-[12px] border border-hair bg-surface p-[1.3rem]"
          >
            <blockquote className="m-0 font-display font-normal text-[1.02rem] leading-[1.4] text-ink">{q.quote}</blockquote>
            <figcaption className="flex items-center gap-[0.7rem]">
              <span
                className="flex size-[34px] flex-shrink-0 items-center justify-center rounded-full bg-accent-weak font-mono text-[0.62rem] tracking-[0.04em] text-accent"
                aria-hidden="true"
              >
                {q.name
                  .split(/[.\s]+/)
                  .filter(Boolean)
                  .map((p) => p[0])
                  .join("")}
              </span>
              <span className="flex min-w-0 flex-col">
                <span className="font-mono text-[0.76rem] text-ink">{q.name}</span>
                <span className="font-mono text-[0.62rem] text-ink-mute">
                  {q.role} · {q.org} <span className="text-accent">× digiquant</span>
                </span>
              </span>
            </figcaption>
          </figure>
        ))}
      </div>

      <div
        className="mt-[1.4rem] flex flex-wrap items-center gap-x-[1.4rem] gap-y-[0.5rem] border-t border-hair pt-[1.1rem] font-mono text-[0.74rem] text-ink-soft"
        aria-label="Illustrative organizations"
      >
        <span className="text-[0.58rem] uppercase tracking-[0.1em] text-ink-mute">trusted by</span>
        {ORGS.map((o) => (
          <span key={o}>{o}</span>
        ))}
      </div>
    </section>
  );
}
