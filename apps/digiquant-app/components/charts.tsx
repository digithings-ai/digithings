/**
 * Chart primitives. SVG on a 0–100 viewBox stretched to the container (non-scaling strokes),
 * so they fill any cell and stay crisp at any zoom. Non-finite points are dropped, never zeroed.
 * Axis labels are HTML, not SVG text, so they don't distort.
 */
type Pt = number | null | undefined;
const fin = (v: Pt): v is number => typeof v === 'number' && Number.isFinite(v);

export type LineSeries = { name: string; values: Pt[]; tone?: 'accent' | 'soft' | 'up' | 'down' };
const stroke = { accent: 'var(--accent)', soft: 'var(--ink-soft)', up: 'var(--up)', down: 'var(--down)' };

function range(all: number[]) {
  const lo = Math.min(...all), hi = Math.max(...all);
  const pad = (hi - lo || Math.abs(hi) || 1) * 0.06;
  return { lo: lo - pad, hi: hi + pad };
}

/** Multi-series line chart with min/max axis labels and a last-value dot per series. */
export function LineChart({ series, labels, height = 140, fmt = (v: number) => v.toFixed(2) }: {
  series: LineSeries[];
  /** x labels aligned to values (first and last are shown). */
  labels?: string[];
  height?: number;
  fmt?: (v: number) => string;
}) {
  const live = series.map((s) => ({ ...s, pts: s.values.map((v, i) => (fin(v) ? { i, v } : null)).filter((p): p is { i: number; v: number } => p !== null) }));
  const all = live.flatMap((s) => s.pts.map((p) => p.v));
  const n = Math.max(0, ...series.map((s) => s.values.length));
  if (all.length < 2 || n < 2) return <p className="note mute">not enough points</p>;
  const { lo, hi } = range(all);
  const X = (i: number) => ((i / (n - 1)) * 100).toFixed(2);
  const Y = (v: number) => (100 - ((v - lo) / (hi - lo)) * 100).toFixed(2);
  return (
    <div className="chart">
      <div className="chart-y mono"><span>{fmt(hi)}</span><span>{fmt(lo)}</span></div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} role="img" aria-label={series.map((s) => s.name).join(', ')}>
        {[25, 50, 75].map((g) => <line key={g} x1="0" x2="100" y1={g} y2={g} stroke="var(--hair)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
        {live.map((s) => (
          <polyline key={s.name} fill="none" stroke={stroke[s.tone ?? 'accent']} strokeWidth="1.2" vectorEffect="non-scaling-stroke" points={s.pts.map((p) => `${X(p.i)},${Y(p.v)}`).join(' ')} />
        ))}
      </svg>
      {labels?.length ? <div className="chart-x mono"><span>{labels[0]}</span><span>{labels[labels.length - 1]}</span></div> : null}
      {series.length > 1 ? <div className="chart-k mono">{series.map((s) => <span key={s.name} style={{ color: stroke[s.tone ?? 'accent'] }}>{s.name}</span>)}</div> : null}
    </div>
  );
}

export type Bar = { t: string; o: Pt; h: Pt; l: Pt; c: Pt; v?: Pt };

/** Candles with an optional volume strip. Bars missing any of o/h/l/c are skipped. */
export function Candles({ bars, height = 160 }: { bars: Bar[]; height?: number }) {
  const ok = bars.filter((b) => fin(b.o) && fin(b.h) && fin(b.l) && fin(b.c)) as (Bar & { o: number; h: number; l: number; c: number })[];
  if (ok.length < 2) return <p className="note mute">not enough bars</p>;
  const { lo, hi } = range(ok.flatMap((b) => [b.h, b.l]));
  const Y = (v: number) => 100 - ((v - lo) / (hi - lo)) * 100;
  const w = 100 / ok.length;
  const vmax = Math.max(0, ...ok.map((b) => (fin(b.v) ? b.v : 0)));
  return (
    <div className="chart">
      <div className="chart-y mono"><span>{hi.toFixed(2)}</span><span>{lo.toFixed(2)}</span></div>
      <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} role="img" aria-label="price bars">
        {ok.map((b, i) => {
          const x = i * w + w / 2, up = b.c >= b.o, col = up ? 'var(--up)' : 'var(--down)';
          return (
            <g key={`${b.t}:${i}`} stroke={col} fill={col} vectorEffect="non-scaling-stroke">
              <line x1={x} x2={x} y1={Y(b.h)} y2={Y(b.l)} strokeWidth="1" vectorEffect="non-scaling-stroke" />
              <rect x={x - w * 0.3} width={w * 0.6} y={Math.min(Y(b.o), Y(b.c))} height={Math.max(0.4, Math.abs(Y(b.o) - Y(b.c)))} stroke="none" />
            </g>
          );
        })}
      </svg>
      {vmax > 0 ? (
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height: 28 }} role="img" aria-label="volume">
          {ok.map((b, i) => (fin(b.v) ? <rect key={`${b.t}:${i}`} x={i * w + w * 0.2} width={w * 0.6} y={100 - (b.v / vmax) * 100} height={(b.v / vmax) * 100} fill={b.c >= b.o ? "var(--up)" : "var(--down)"} /> : null))}
        </svg>
      ) : null}
      <div className="chart-x mono"><span>{ok[0].t}</span><span>{ok[ok.length - 1].t}</span></div>
    </div>
  );
}
