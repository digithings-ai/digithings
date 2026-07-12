/**
 * DotMatrixStat — a single metric rendered as a hardware-style LED grid,
 * promoted from the design reference (data/dot-matrix-stat). A cols×rows
 * field of dots lights the first N to encode a percentage, paired with a
 * mono label / value / note column. The lit dots wear the module accent
 * (scope with an `accent-<module>` livery class via className) and glow.
 * The dot field is pure CSS/DOM — no canvas — and decorative (aria-hidden);
 * the value is real text. Server component — no state, no effects.
 *
 * Wiring (in the consuming app):
 *   globals.css   @import "@digithings/web/styles/data-layout.css";
 *                 @source "<path-to>/digiweb/web/src/components/data-layout";
 */
export type DotMatrixStatProps = {
  /** Mono micro-caps label above the value — "Signal confidence". */
  label: string;
  /** The figure itself, preformatted — "67%". */
  value: string;
  /** Percentage of the field to light, 0–100. */
  percent: number;
  /** One quiet sentence under the value. */
  note?: string;
  /** Dot columns in the LED field. */
  cols?: number;
  /** Dot rows in the LED field. */
  rows?: number;
  className?: string;
};

export function DotMatrixStat({
  label,
  value,
  percent,
  note,
  cols = 12,
  rows = 8,
  className,
}: DotMatrixStatProps) {
  const total = cols * rows;
  const lit = Math.min(total, Math.max(0, Math.round((percent / 100) * total)));
  return (
    <div
      className={`grid grid-cols-[180px_1fr] gap-[1.1rem] rounded-[12px] border border-hair bg-surface p-[1.1rem] max-[900px]:grid-cols-1${
        className ? ` ${className}` : ""
      }`}
    >
      <div
        className="dms-grid"
        style={{ gridTemplateColumns: `repeat(${cols}, minmax(0, 1fr))` }}
        aria-hidden="true"
      >
        {Array.from({ length: total }, (_, i) => (
          <span key={i} className={i < lit ? "dms-dot on" : "dms-dot"} />
        ))}
      </div>
      <div>
        <p className="font-mono text-[0.72rem] uppercase tracking-[0.08em] text-ink-mute">
          {label}
        </p>
        <p className="mt-[0.2rem] font-mono text-[clamp(2rem,5vw,2.8rem)]">{value}</p>
        {note ? <p className="mt-[0.55rem] max-w-[50ch] text-ink-soft">{note}</p> : null}
      </div>
    </div>
  );
}
