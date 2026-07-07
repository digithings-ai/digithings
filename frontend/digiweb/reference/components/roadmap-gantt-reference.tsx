/**
 * Roadmap Gantt — initiative bars laid across a month axis. Each row is owned
 * by a module and wears its livery, so the bar hues are identifiers, not
 * decoration (canon §13); a hairline "now" marker cuts the timeline at a
 * fractional month offset. Scrolls horizontally when narrow. Static display
 * template.
 */
const MONTHS = ["Jan", "Feb", "Mar", "Apr", "May", "Jun", "Jul", "Aug"];

// start/end are 1-based month indices (inclusive). Each initiative is owned by
// a module and wears its livery — chart series as identifiers (canon §13).
type Initiative = { label: string; livery: string; start: number; end: number };

const ROWS: Initiative[] = [
  { label: "atlas research loop", livery: "atlas", start: 1, end: 3 },
  { label: "Kelly-capped sizing", livery: "digiquant", start: 2, end: 4 },
  { label: "Live broker adapters", livery: "hermes", start: 3, end: 6 },
  { label: "olympus dashboard", livery: "kairos", start: 5, end: 8 },
  { label: "digichat embed", livery: "digichat", start: 6, end: 8 },
];

// "now" marker sits at the end of month 4 (Apr/May boundary).
const NOW_MONTH = 4;

export function RoadmapGanttReference() {
  return (
    <section className="section-block roadmap-gantt">
      <p className="kicker">{"// roadmap"}</p>
      <h2 className="title">Initiatives across the quarter.</h2>
      <p className="section-copy">
        The Gantt band: initiative bars spanning a month axis, each owned by a module and wearing
        its livery — here the bars are chart series, so distinguishable hues are identifiers, not
        decoration (canon §13). A hairline &ldquo;now&rdquo; marker cuts the timeline.
      </p>

      <div className="mt-[1.2rem] overflow-x-auto">
        <div className="rg" style={{ ["--rg-cols" as string]: MONTHS.length }}>
          <div className="rg-head">
            <span className="rg-corner" aria-hidden="true" />
            {MONTHS.map((mo) => (
              <span key={mo} className="rg-month">
                {mo}
              </span>
            ))}
          </div>

          <div className="rg-body">
            <span className="rg-now" style={{ ["--rg-now" as string]: NOW_MONTH }} aria-hidden="true" />
            {ROWS.map((r) => (
              <div className="rg-row" key={r.label}>
                <span className="rg-label">{r.label}</span>
                <span
                  className={`rg-bar accent-${r.livery}`}
                  style={{ gridColumn: `${r.start + 1} / ${r.end + 2}` }}
                >
                  <span className="rg-bar-span">
                    {MONTHS[r.start - 1]}–{MONTHS[r.end - 1]}
                  </span>
                </span>
              </div>
            ))}
          </div>
        </div>
      </div>
    </section>
  );
}
