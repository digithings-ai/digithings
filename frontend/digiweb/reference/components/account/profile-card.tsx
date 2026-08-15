/**
 * Profile — an account rendered as a record, not a billboard: a serif name and
 * mono meta over a hairline stat strip, with a recent-activity log underneath
 * that leads with timestamps and follows with verbs. Static example data — a
 * display template, no live account behind it.
 */
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

      <div className="mt-[1.2rem] rounded-[12px] border border-hair bg-surface p-[1.2rem]">
        <div className="flex items-center gap-4">
          <span
            className="inline-flex size-12 flex-shrink-0 items-center justify-center rounded-full bg-accent-weak font-mono text-[0.85rem] uppercase tracking-[0.06em] text-accent"
            aria-hidden="true"
          >
            cs
          </span>
          <div>
            <h3 className="font-display text-[1.35rem] font-normal leading-[1.1] tracking-[-0.013em]">
              Chris Stefan
            </h3>
            <p className="mt-[0.2rem] font-mono text-[0.7rem] tracking-[0.04em] text-ink-mute">
              cstefan · admin · joined 2026-03
            </p>
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

        <p className="mt-[1.1rem] font-mono text-[0.62rem] uppercase tracking-[0.08em] text-ink-mute">
          recent activity
        </p>
        <ul className="acct-activity">
          {ACTIVITY.map((item) => (
            <li key={item.at}>
              <span className="text-ink-mute">{item.at}</span>
              <span className="text-ink-soft">{item.entry}</span>
            </li>
          ))}
        </ul>
      </div>
    </section>
  );
}
