import type { ChartType, PanelPoint, PanelShape, PanelUnit } from "../../../../clients/digiquant-tui/src/pages/panel-shape";

/** Draws one panel's points. Hairline axes, no gridlines, no legend. A renderer swap keeps these props. */

const W = 320;
const H = 160;
const PAD = { top: 8, right: 8, bottom: 18, left: 40 };
const INK = "var(--ink)";
const MUTE = "var(--ink-mute)";
const HAIR = "var(--hair)";
const UP = "var(--up)";
const DOWN = "var(--down)";
/** Slice fills step down from ink so neighbours stay apart without a palette. */
const SLICE = [100, 72, 52, 38, 28, 20];

export function unitText(value: number, unit: PanelUnit): string {
  if (unit === "pct") return `${value.toFixed(2)}%`;
  if (unit === "bp") return `${value.toFixed(1)} bp`;
  return value.toFixed(2);
}

function sliceFill(index: number): string {
  return `color-mix(in srgb, ${INK} ${SLICE[index % SLICE.length]}%, transparent)`;
}

function bounds(points: PanelPoint[], withZero: boolean): { lo: number; hi: number } {
  const values = points.map((point) => point.value);
  let lo = Math.min(...values, ...(withZero ? [0] : []));
  let hi = Math.max(...values, ...(withZero ? [0] : []));
  if (lo === hi) {
    lo -= 1;
    hi += 1;
  }
  return { lo, hi };
}

function Axes({ lo, hi, unit, first, last }: { lo: number; hi: number; unit: PanelUnit; first: string; last: string }) {
  const bottom = H - PAD.bottom;
  return (
    <g fontSize={9} fill={MUTE} fontFamily="var(--font-mono, monospace)">
      <line x1={PAD.left} x2={W - PAD.right} y1={bottom} y2={bottom} stroke={HAIR} />
      <text x={PAD.left - 4} y={PAD.top + 6} textAnchor="end">{unitText(hi, unit)}</text>
      <text x={PAD.left - 4} y={bottom} textAnchor="end">{unitText(lo, unit)}</text>
      <text x={PAD.left} y={H - 4}>{first}</text>
      <text x={W - PAD.right} y={H - 4} textAnchor="end">{last}</text>
    </g>
  );
}

function SeriesChart({ points, unit, type }: { points: PanelPoint[]; unit: PanelUnit; type: "line" | "area" | "bar" }) {
  const { lo, hi } = bounds(points, type !== "line");
  const span = W - PAD.left - PAD.right;
  const tall = H - PAD.top - PAD.bottom;
  const y = (value: number) => PAD.top + ((hi - value) / (hi - lo)) * tall;
  const first = points[0]?.label ?? "";
  const last = points.at(-1)?.label ?? "";

  if (type === "bar") {
    const step = span / points.length;
    const zero = y(0);
    return (
      <>
        <Axes lo={lo} hi={hi} unit={unit} first={first} last={last} />
        {points.map((point, index) => (
          <rect
            key={point.label}
            x={PAD.left + index * step + step * 0.1}
            width={Math.max(step * 0.8, 0.5)}
            y={Math.min(y(point.value), zero)}
            height={Math.max(Math.abs(y(point.value) - zero), 0.5)}
            fill={point.value < 0 ? DOWN : UP}
          >
            <title>{`${point.label}  ${unitText(point.value, unit)}`}</title>
          </rect>
        ))}
      </>
    );
  }

  const x = (index: number) => PAD.left + (points.length === 1 ? 0 : (index / (points.length - 1)) * span);
  const line = points.map((point, index) => `${index === 0 ? "M" : "L"}${x(index).toFixed(2)},${y(point.value).toFixed(2)}`).join("");
  const base = y(Math.max(lo, Math.min(0, hi)));
  const area = `${line}L${x(points.length - 1).toFixed(2)},${base.toFixed(2)}L${x(0).toFixed(2)},${base.toFixed(2)}Z`;
  return (
    <>
      <Axes lo={lo} hi={hi} unit={unit} first={first} last={last} />
      {type === "area" ? <path d={area} fill={`color-mix(in srgb, ${INK} 14%, transparent)`} /> : null}
      <path d={line} fill="none" stroke={INK} strokeWidth={1.25} vectorEffect="non-scaling-stroke" />
    </>
  );
}

function RankBars({ points, unit }: { points: PanelPoint[]; unit: PanelUnit }) {
  const { lo, hi } = bounds(points, true);
  const left = 56;
  const right = W - 52;
  const x = (value: number) => left + ((value - lo) / (hi - lo)) * (right - left);
  const row = Math.min((H - 4) / points.length, 18);
  const zero = x(0);
  return (
    <g fontSize={9} fontFamily="var(--font-mono, monospace)">
      <line x1={zero} x2={zero} y1={0} y2={row * points.length} stroke={HAIR} />
      {points.map((point, index) => {
        const top = index * row;
        const end = x(point.value);
        return (
          <g key={point.label}>
            <text x={left - 4} y={top + row * 0.68} textAnchor="end" fill={MUTE}>{point.label}</text>
            <rect x={Math.min(zero, end)} y={top + row * 0.18} width={Math.max(Math.abs(end - zero), 0.5)} height={row * 0.64} fill={point.value < 0 ? DOWN : UP} />
            <text x={right + 4} y={top + row * 0.68} fill={INK}>{unitText(point.value, unit)}</text>
          </g>
        );
      })}
    </g>
  );
}

function Donut({ points, unit }: { points: PanelPoint[]; unit: PanelUnit }) {
  const total = points.reduce((sum, point) => sum + point.value, 0);
  const cx = H / 2;
  const cy = H / 2;
  const r = H / 2 - 6;
  const inner = r * 0.6;
  const arc = (a: number, radius: number) => `${(cx + radius * Math.cos(a)).toFixed(2)},${(cy + radius * Math.sin(a)).toFixed(2)}`;
  const sweeps = points.map((point) => (total > 0 ? (point.value / total) * Math.PI * 2 : 0));
  const starts = sweeps.map((_, index) => -Math.PI / 2 + sweeps.slice(0, index).reduce((sum, sweep) => sum + sweep, 0));
  const legend = points.slice(0, 8);
  return (
    <g fontSize={9} fontFamily="var(--font-mono, monospace)">
      {points.map((point, index) => {
        const start = starts[index] ?? 0;
        const end = start + Math.min(sweeps[index] ?? 0, Math.PI * 2 - 1e-4);
        const large = end - start > Math.PI ? 1 : 0;
        const d = `M${arc(start, r)}A${r},${r} 0 ${large} 1 ${arc(end, r)}L${arc(end, inner)}A${inner},${inner} 0 ${large} 0 ${arc(start, inner)}Z`;
        return (
          <path key={point.label} d={d} fill={sliceFill(index)} stroke="var(--surface)" strokeWidth={1}>
            <title>{`${point.label}  ${unitText(point.value, unit)}`}</title>
          </path>
        );
      })}
      {legend.map((point, index) => (
        <g key={point.label} transform={`translate(${H + 8}, ${12 + index * 17})`}>
          <rect width={8} height={8} y={-7} fill={sliceFill(index)} />
          <text x={12} fill={MUTE}>{point.label}</text>
          <text x={W - H - 16} textAnchor="end" fill={INK}>{unitText(point.value, unit)}</text>
        </g>
      ))}
    </g>
  );
}

/** Slice-and-dice treemap: rows of slices, each row filled left to right. */
function Treemap({ points, unit }: { points: PanelPoint[]; unit: PanelUnit }) {
  const total = points.reduce((sum, point) => sum + point.value, 0);
  if (total <= 0) return null;
  const widths = points.map((point) => (point.value / total) * W);
  const lefts = widths.map((_, index) => widths.slice(0, index).reduce((sum, width) => sum + width, 0));
  return (
    <g fontSize={9} fontFamily="var(--font-mono, monospace)">
      {points.map((point, index) => {
        const width = widths[index] ?? 0;
        const x = lefts[index] ?? 0;
        return (
          <g key={point.label}>
            <rect x={x} y={0} width={Math.max(width, 0.5)} height={H} fill={sliceFill(index)} stroke="var(--surface)" strokeWidth={1}>
              <title>{`${point.label}  ${unitText(point.value, unit)}`}</title>
            </rect>
            {width > 34 ? (
              <>
                <text x={x + 4} y={12} fill="var(--surface)">{point.label}</text>
                <text x={x + 4} y={24} fill="var(--surface)">{unitText(point.value, unit)}</text>
              </>
            ) : null}
          </g>
        );
      })}
    </g>
  );
}

/** A series bar is a column per date or tenor. A composition or ranking bar is one labelled row per name. */
export function PanelChart({ shape, type, points, unit, label }: { shape: PanelShape; type: ChartType; points: PanelPoint[]; unit: PanelUnit; label: string }) {
  const ranked = type === "bar" && shape !== "series";
  return (
    <svg
      role="img"
      aria-label={label}
      data-chart={type}
      viewBox={`0 0 ${W} ${H}`}
      preserveAspectRatio="xMidYMid meet"
      className="block h-full min-h-[10rem] w-full"
    >
      {type === "donut" ? (
        <Donut points={points} unit={unit} />
      ) : type === "treemap" ? (
        <Treemap points={points} unit={unit} />
      ) : ranked ? (
        <RankBars points={points} unit={unit} />
      ) : (
        <SeriesChart points={points} unit={unit} type={type} />
      )}
    </svg>
  );
}
