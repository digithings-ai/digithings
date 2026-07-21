/**
 * Portfolio workspace — the page-level grammar for a research-driven book: a
 * restrained command band establishes exposure, then a full-width position
 * ledger carries only the information needed to monitor and follow a holding.
 * Static data, token-only dress.
 */

const POSITIONS = [
  { ticker: "XLE", category: "energy", weight: "17.2%", conviction: 2, day: "+0.8%", unrealized: "+4.8%", stop: "−8%", target: "+15%", tone: "up" },
  { ticker: "XLF", category: "financials", weight: "17.2%", conviction: 2, day: "−0.2%", unrealized: "+1.2%", stop: "−6%", target: "+12%", tone: "up" },
  { ticker: "UUP", category: "fx", weight: "15.2%", conviction: 3, day: "+0.3%", unrealized: "+2.7%", stop: "−5%", target: "+9%", tone: "up" },
  { ticker: "XLRE", category: "real estate", weight: "12.9%", conviction: 2, day: "−0.5%", unrealized: "−0.9%", stop: "−7%", target: "+11%", tone: "down" },
  { ticker: "XLV", category: "healthcare", weight: "12.9%", conviction: 2, day: "+0.1%", unrealized: "+0.4%", stop: "−6%", target: "+10%", tone: "up" },
];

export function PortfolioWorkspaceReference() {
  return (
    <section className="section-block pw-ref" id="portfolio-workspace">
      <p className="kicker">{"// portfolio workspace"}</p>
      <h2 className="title">The book reads like a decision surface.</h2>
      <p className="section-copy">
        The canonical page composition for an active portfolio: one exposure figure, the position
        count, and a ledger that makes allocation, risk, performance, and provenance easy to scan.
      </p>

      <div className="pw-frame">
        <header className="pw-command">
          <div className="pw-command__identity">
            <span className="pw-label">invested</span>
            <strong>84.8%</strong>
          </div>
          <dl className="pw-command__metrics">
            <div>
              <dt>positions</dt>
              <dd>11</dd>
            </div>
          </dl>
          <div className="pw-command__stamp">
            <span>as of</span>
            <strong>19 JUL 2026</strong>
          </div>
        </header>

        <section className="pw-ledger" aria-labelledby="pw-ledger-title">
          <div className="pw-section-head">
            <div>
              <span className="pw-label">active allocation</span>
              <h3 id="pw-ledger-title">Positions</h3>
            </div>
            <span className="pw-section-meta">allocation · performance · risk · provenance</span>
          </div>

          <div className="pw-table-wrap">
            <table className="pw-table">
              <thead>
                <tr>
                  <th>ticker</th>
                  <th>category</th>
                  <th>allocation</th>
                  <th>conviction</th>
                  <th>day</th>
                  <th>unrealized</th>
                  <th>stop / target</th>
                  <th>follow</th>
                </tr>
              </thead>
              <tbody>
                {POSITIONS.map((position) => (
                  <tr key={position.ticker}>
                    <td><strong>{position.ticker}</strong></td>
                    <td>{position.category}</td>
                    <td>{position.weight}</td>
                    <td>
                      <span className="pw-conviction" aria-label={`Conviction ${position.conviction} of 3`}>
                        {[1, 2, 3].map((level) => <i key={level} data-filled={level <= position.conviction} />)}
                      </span>
                    </td>
                    <td>{position.day}</td>
                    <td className={position.tone === "up" ? "text-up" : "text-down"}>
                      {position.unrealized}
                    </td>
                    <td>{position.stop} / {position.target}</td>
                    <td><span className="pw-follow">decision · dossier</span></td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </section>
      </div>
    </section>
  );
}
