const ACTIVITY = [
  { at: "2026-07-05 14:12", entry: "deployed hermes sub-graph to staging" },
  { at: "2026-07-04 09:48", entry: "ran 24 backtests on momentum-carry basket" },
  { at: "2026-07-02 17:03", entry: "rotated digikey API token" },
  { at: "2026-06-30 11:26", entry: "invited m.tanaka as analyst" },
];

export function ProfileCard() {
  return (
    <section className="section-block">
      <p className="kicker">{"// profile"}</p>
      <h2 className="title">Identity, kept like a ledger.</h2>
      <p className="section-copy">
        A profile is a record, not a billboard: serif name, mono meta, a hairline stat strip, and
        the recent activity log underneath — timestamps first, verbs second.
      </p>

      <div className="acct-profile">
        <div className="acct-profile-head">
          <span className="acct-avatar" aria-hidden="true">
            cs
          </span>
          <div>
            <h3 className="acct-profile-name">Chris Stefan</h3>
            <p className="acct-profile-meta">cstefan · admin · joined 2026-03</p>
          </div>
        </div>

        <div className="acct-stat-strip">
          <span>
            <strong>14</strong> strategies
          </span>
          <span>
            <strong>312</strong> backtests
          </span>
          <span>
            <strong>4</strong> modules
          </span>
        </div>

        <p className="acct-activity-label">recent activity</p>
        <ul className="acct-activity">
          {ACTIVITY.map((item) => (
            <li key={item.at}>
              <span className="acct-activity-at">{item.at}</span>
              <span className="acct-activity-entry">{item.entry}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
