const COLS = 12;
const ROWS = 8;
const ACTIVE = 67;

export function DotMatrixStat() {
  return (
    <section className="section-block" id="dot-matrix-stat">
      <div className="section-head">
        <p className="kicker">{"// dot matrix stat"}</p>
        <h2 className="title">One metric. Hardware-grade readability.</h2>
      </div>
      <div className="dot-matrix-card">
        <div className="dot-matrix-grid" aria-hidden="true">
          {Array.from({ length: COLS * ROWS }, (_, i) => (
            <span key={i} className={i < ACTIVE ? "dot on" : "dot"} />
          ))}
        </div>
        <div className="dot-matrix-copy">
          <p className="label">Signal confidence</p>
          <p className="value">67%</p>
          <p className="note">Mapped to module accent, tabular, and glance-readable on dense dashboards.</p>
        </div>
      </div>
    </section>
  );
}
