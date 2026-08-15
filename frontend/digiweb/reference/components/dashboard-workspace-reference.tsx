/**
 * Dashboard workspace — the page-level composition for dense operational and
 * research surfaces: one command band establishes the primary state, compact
 * metrics add context, and a flat hairline ledger carries the working detail.
 * Static data, token-only dress.
 */

const DECISIONS = [
  {
    subject: "USD strength",
    decision: "Maintain long-dollar expression",
    state: "monitor",
    owner: "Hermes",
    impact: "+2.7%",
    tone: "up",
    updated: "09:42",
  },
  {
    subject: "Advanced materials",
    decision: "Add only after demand confirmation",
    state: "active view",
    owner: "Atlas",
    impact: "+0.4%",
    tone: "up",
    updated: "08:15",
  },
  {
    subject: "Real estate duration",
    decision: "Hold below target allocation",
    state: "watch",
    owner: "Hermes",
    impact: "−0.9%",
    tone: "down",
    updated: "07:50",
  },
] as const;

export function DashboardWorkspaceReference() {
  return (
    <section className="section-block dw-ref" id="dashboard-workspace">
      <p className="kicker">{"// dashboard workspace"}</p>
      <h2 className="title">One state, then the decisions behind it.</h2>
      <p className="section-copy">
        The canonical page composition for a working dashboard: a restrained command band names
        the primary state, a small metric group adds context, and a full-width ledger makes the
        underlying decisions easy to scan without stacking decorative cards.
      </p>

      <div className="dw-frame">
        <header className="dw-command">
          <div className="dw-command__identity">
            <span className="dw-label">invested</span>
            <strong>84.8%</strong>
            <span>selective risk-on</span>
          </div>

          <dl className="dw-command__metrics">
            <div>
              <dt>positions</dt>
              <dd>11</dd>
            </div>
            <div>
              <dt>active views</dt>
              <dd>2</dd>
            </div>
          </dl>

          <div className="dw-command__stamp">
            <span>as of</span>
            <strong>21 JUL 2026</strong>
          </div>
        </header>

        <section className="dw-ledger" aria-labelledby="dw-ledger-title">
          <div className="dw-section-head">
            <div>
              <span className="dw-label">decision monitor</span>
              <h3 id="dw-ledger-title">Current calls</h3>
            </div>
            <span className="dw-section-meta">state · ownership · impact · provenance</span>
          </div>

          <div className="dw-table-wrap">
            <table className="dw-table">
              <thead>
                <tr>
                  <th scope="col">subject</th>
                  <th scope="col">decision</th>
                  <th scope="col">state</th>
                  <th scope="col">owner</th>
                  <th scope="col">return</th>
                  <th scope="col">updated</th>
                  <th scope="col">follow</th>
                </tr>
              </thead>
              <tbody>
                {DECISIONS.map((item) => (
                  <tr key={item.subject}>
                    <td><strong>{item.subject}</strong></td>
                    <td>{item.decision}</td>
                    <td><span className="dw-state">{item.state}</span></td>
                    <td>{item.owner}</td>
                    <td className={item.tone === "up" ? "text-up" : "text-down"}>
                      {item.impact}
                    </td>
                    <td>{item.updated}</td>
                    <td><span className="dw-follow">brief · dossier</span></td>
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