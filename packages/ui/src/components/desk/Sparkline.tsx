export type SparklineProps = {
  /** The series in reading order. Non-finite points are dropped, not zero-filled. */
  values: (number | null | undefined)[];
  height?: number;
  /** Accessible name. Defaults to a summary derived from the points that are drawn. */
  label?: string;
  /** The figure is printed next to the line — hide the drawing from assistive tech. */
  decorative?: boolean;
  /** Shown when there are fewer than two finite points to draw. */
  placeholder?: string;
};

/** Compact read of a plotted value: integers as-is, floats to four places with
 *  trailing zeros stripped. Presentation only — no point is invented. */
const read = (value: number): string =>
  Number.isInteger(value) ? String(value) : String(Number(value.toFixed(4)));

export function Sparkline({
  values: raw,
  height = 56,
  label,
  decorative,
  placeholder = "not enough points",
}: SparklineProps) {
  const values = (raw ?? []).filter(
    (value): value is number => typeof value === "number" && Number.isFinite(value),
  );
  if (values.length < 2) {
    return <p className="font-mono text-[0.72rem] text-ink-mute">{placeholder}</p>;
  }

  const low = Math.min(...values);
  const high = Math.max(...values);
  const span = high - low || 1;
  const points = values
    .map((value, index) => {
      const x = (index / (values.length - 1)) * 100;
      const y = 100 - ((value - low) / span) * 100;
      return `${x.toFixed(2)},${y.toFixed(2)}`;
    })
    .join(" ");
  const summary = `sparkline, ${values.length} points, ${read(values[0])} to ${read(values[values.length - 1])}, low ${read(low)}, high ${read(high)}`;

  return (
    <svg
      viewBox="0 0 100 100"
      preserveAspectRatio="none"
      role={decorative ? undefined : "img"}
      aria-hidden={decorative || undefined}
      aria-label={decorative ? undefined : (label ?? summary)}
      style={{ height }}
      className="block w-full overflow-visible text-accent"
    >
      <polyline
        points={points}
        fill="none"
        stroke="currentColor"
        strokeWidth="1.2"
        vectorEffect="non-scaling-stroke"
      />
    </svg>
  );
}
