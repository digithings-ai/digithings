const MODELS = [
  { model: "grok-parity-4.3", context: "256k", price: "$3.00" },
  { model: "grok-build-0.1", context: "128k", price: "$0.85" },
  { model: "grok-fast-0.2", context: "64k", price: "$0.20" },
];

export function PricingReference() {
  return (
    <section className="section-block pricing-ref">
      <p className="kicker">{"// pricing"}</p>
      <h2 className="title">Precision over persuasion.</h2>
      <p className="section-copy">
        x.ai runs exactly two paths — self-serve vs. talk to sales — with one filled CTA total.
        That is the open-core shape: self-hosted vs. managed. The per-unit table below rides the
        same hairline-row, mono-numeral voice as our tearsheets.
      </p>

      <div className="pricing-paths">
        <div className="pricing-path">
          <p className="pricing-path-title">Self-hosted</p>
          <p className="pricing-path-copy">
            Open core · BYOK · audit-on by default. All modules, usage-based inference.
          </p>
          <button type="button" className="btn-ghost">
            Read the docs
          </button>
        </div>
        <div className="pricing-path featured">
          <p className="pricing-path-title">Managed</p>
          <p className="pricing-path-copy">
            Onboarding, custom limits, SSO, audit log, SLA-backed uptime.
          </p>
          <button type="button" className="btn-primary">
            Contact sales
          </button>
        </div>
      </div>

      <p className="trust-line">
        Free for your first 30 days. No credit card required. Synced with your GitHub account.
      </p>

      <table className="precision-table">
        <thead>
          <tr>
            <th>Model</th>
            <th>Context</th>
            <th>$/M tokens</th>
          </tr>
        </thead>
        <tbody>
          {MODELS.map((row) => (
            <tr key={row.model}>
              <td>{row.model}</td>
              <td>{row.context}</td>
              <td>{row.price}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </section>
  );
}
