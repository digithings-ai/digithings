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
      <p className="tw-badge">Example data · not live</p>

      <div className="tw-grid">
        {QUOTES.map((q) => (
          <figure key={q.name} className="tw-card">
            <blockquote className="tw-quote">{q.quote}</blockquote>
            <figcaption className="tw-cite">
              <span className="tw-avatar" aria-hidden="true">
                {q.name
                  .split(/[.\s]+/)
                  .filter(Boolean)
                  .map((p) => p[0])
                  .join("")}
              </span>
              <span className="tw-who">
                <span className="tw-name">{q.name}</span>
                <span className="tw-role">
                  {q.role} · {q.org} <span className="tw-x">× digiquant</span>
                </span>
              </span>
            </figcaption>
          </figure>
        ))}
      </div>

      <div className="tw-orgs" aria-label="Illustrative organizations">
        <span className="tw-orgs-label">trusted by</span>
        {ORGS.map((o) => (
          <span key={o} className="tw-org">
            {o}
          </span>
        ))}
      </div>
    </section>
  );
}
