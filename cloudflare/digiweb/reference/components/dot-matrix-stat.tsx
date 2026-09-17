/**
 * Dot-matrix stat — a single metric rendered as a hardware-style LED grid.
 * A 12×8 field of dots lights the first N to encode a percentage, paired with
 * a mono label / value / note column. The lit dots wear the module accent and
 * glow; the read is glance-legible on dense dashboards. Consumes the shared
 * <DotMatrixStat/> primitive from @digithings/web. Static display template.
 */
import { DotMatrixStat as DotMatrixStatCard } from "@digithings/web";

export function DotMatrixStat() {
  return (
    <section className="section-block" id="dot-matrix-stat">
      <div className="section-head">
        <p className="kicker">{"// dot matrix stat"}</p>
        <h2 className="title">One metric. Hardware-grade readability.</h2>
      </div>
      <DotMatrixStatCard
        className="mt-[1.2rem]"
        label="Signal confidence"
        value="67%"
        percent={67}
        note="Mapped to module accent, tabular, and glance-readable on dense dashboards."
      />
    </section>
  );
}
