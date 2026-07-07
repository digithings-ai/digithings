/**
 * Dot-matrix stat — a single metric rendered as a hardware-style LED grid.
 * A 12×8 field of dots lights the first N to encode a percentage, paired with
 * a mono label / value / note column. The lit dots wear the module accent and
 * glow; the read is glance-legible on dense dashboards. Static display template.
 */
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
      <div className="mt-[1.2rem] grid grid-cols-[180px_1fr] gap-[1.1rem] rounded-[12px] border border-hair bg-surface p-[1.1rem] max-[900px]:grid-cols-1">
        <div className="dot-matrix-grid" aria-hidden="true">
          {Array.from({ length: COLS * ROWS }, (_, i) => (
            <span key={i} className={i < ACTIVE ? "dot on" : "dot"} />
          ))}
        </div>
        <div>
          <p className="font-mono text-[0.72rem] uppercase tracking-[0.08em] text-ink-mute">Signal confidence</p>
          <p className="mt-[0.2rem] font-mono text-[clamp(2rem,5vw,2.8rem)]">67%</p>
          <p className="mt-[0.55rem] max-w-[50ch] text-ink-soft">
            Mapped to module accent, tabular, and glance-readable on dense dashboards.
          </p>
        </div>
      </div>
    </section>
  );
}
