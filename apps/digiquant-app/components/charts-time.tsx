'use client';

import { useState, type KeyboardEvent, type PointerEvent, type ReactNode } from 'react';

/**
 * Dated chart atoms: AreaChart (incl. underwater), BarChart (signed), range tabs, crosshair tooltip.
 * Same 0–100 stretched SVG as charts.tsx. Non-finite values are dropped, never zeroed;
 * empty data renders "—". Crosshair: hover, or focus + ←/→.
 */
export type TPoint = { t: string; v: number | null | undefined };
type Tone = 'accent' | 'up' | 'down';
const col = { accent: 'var(--accent)', up: 'var(--up)', down: 'var(--down)' };
const ok = (v: unknown): v is number => typeof v === 'number' && Number.isFinite(v);
const def = (v: number) => v.toFixed(2);

/* ---- ranges ---- */
export const RANGES = ['1M', '3M', '6M', 'YTD', '1Y', 'ALL'] as const;
export type Range = (typeof RANGES)[number];

/** Points inside the range, measured back from the LAST point's date (not today). Unparsable dates return all. */
export function sliceRange<T extends { t: string }>(pts: T[], r: Range): T[] {
  if (r === 'ALL' || !pts.length) return pts;
  const end = new Date(pts[pts.length - 1].t);
  if (Number.isNaN(end.getTime())) return pts;
  const from = new Date(end);
  if (r === 'YTD') from.setUTCMonth(0, 1);
  else from.setUTCMonth(from.getUTCMonth() - { '1M': 1, '3M': 3, '6M': 6, '1Y': 12 }[r]);
  const cut = from.getTime();
  return pts.filter((p) => { const x = Date.parse(p.t); return Number.isNaN(x) || x >= cut; });
}

export function RangeTabs({ value, onChange, ranges = RANGES }: { value: Range; onChange: (r: Range) => void; ranges?: readonly Range[] }) {
  return (
    <div className="rtabs mono" role="tablist" aria-label="Range">
      {ranges.map((r) => <button key={r} type="button" role="tab" aria-selected={r === value} className={r === value ? 'on' : undefined} onClick={() => onChange(r)}>{r}</button>)}
    </div>
  );
}

/** Range state + tabs for any dated series: `const { shown, tabs } = useRange(points)`. */
export function useRange<T extends { t: string }>(pts: T[], ranges: readonly Range[] = RANGES, initial: Range = 'ALL') {
  const [r, setR] = useState<Range>(ranges.includes(initial) ? initial : ranges[ranges.length - 1]);
  return { range: r, shown: sliceRange(pts, r), tabs: <RangeTabs value={r} onChange={setR} ranges={ranges} /> };
}

/* ---- shared plot with crosshair ---- */
const fmtDate = (t: string, span: number) => {
  const d = new Date(t);
  if (Number.isNaN(d.getTime())) return t;
  const m = d.toLocaleString('en-GB', { month: 'short', timeZone: 'UTC' });
  return span > 400 * 864e5 ? `${m} ${String(d.getUTCFullYear()).slice(2)}` : `${d.getUTCDate()} ${m}`;
};

/** x fractions (0–1) by date when every date parses, else by index. */
function xfrac(ts: string[]): { xf: number[]; span: number } {
  const ms = ts.map((t) => Date.parse(t));
  const n = ts.length;
  if (n > 1 && ms.every((m) => !Number.isNaN(m)) && ms[n - 1] > ms[0]) {
    const span = ms[n - 1] - ms[0];
    return { xf: ms.map((m) => (m - ms[0]) / span), span };
  }
  return { xf: ts.map((_, i) => (n > 1 ? i / (n - 1) : 0.5)), span: 0 };
}

function Plot({ xf, yf, height, label, tip, children }: {
  xf: number[]; yf: (i: number) => number | null; height: number; label: string; tip: (i: number) => ReactNode; children: ReactNode;
}) {
  const [cur, setCur] = useState<number | null>(null);
  const near = (e: PointerEvent<HTMLDivElement>) => {
    const b = e.currentTarget.getBoundingClientRect();
    const f = b.width ? (e.clientX - b.left) / b.width : 0;
    let best = 0;
    xf.forEach((x, i) => { if (Math.abs(x - f) < Math.abs(xf[best] - f)) best = i; });
    setCur(best);
  };
  const key = (e: KeyboardEvent) => {
    if (e.key === 'ArrowLeft' || e.key === 'ArrowRight') {
      e.preventDefault();
      const d = e.key === 'ArrowLeft' ? -1 : 1;
      setCur((c) => Math.max(0, Math.min(xf.length - 1, (c ?? (d < 0 ? xf.length : -1)) + d)));
    } else if (e.key === 'Escape') setCur(null);
  };
  const y = cur == null ? null : yf(cur);
  return (
    <div className="chart-plot" tabIndex={0} role="img" aria-label={label} style={{ height }} onPointerMove={near} onPointerLeave={() => setCur(null)} onKeyDown={key} onBlur={() => setCur(null)}>
      {children}
      {cur != null ? (
        <>
          <div className="chart-cross" style={{ left: `${xf[cur] * 100}%` }} />
          {y != null ? <div className="chart-dot" style={{ left: `${xf[cur] * 100}%`, top: `${y}%` }} /> : null}
          <div className={`chart-tip mono${xf[cur] > 0.6 ? ' flip' : ''}`} style={{ left: `${xf[cur] * 100}%` }} role="status">{tip(cur)}</div>
        </>
      ) : null}
    </div>
  );
}

function XAxis({ ts, xf, span }: { ts: string[]; xf: number[]; span: number }) {
  // 4 ticks at even time fractions, snapped to the nearest real point.
  const ticks = [0, 1 / 3, 2 / 3, 1].map((f) => { let b = 0; xf.forEach((x, i) => { if (Math.abs(x - f) < Math.abs(xf[b] - f)) b = i; }); return b; });
  const uniq = ticks.filter((v, i) => ticks.indexOf(v) === i);
  return <div className="chart-x mono">{uniq.map((i) => <span key={i}>{fmtDate(ts[i], span)}</span>)}</div>;
}

/** Axis-range helper with the same 6% padding as LineChart. */
function pad(lo: number, hi: number) {
  const p = (hi - lo || Math.abs(hi) || 1) * 0.06;
  return { lo: lo - p, hi: hi + p };
}

/**
 * Area chart over dated points. `underwater` plots a ≤0 series (e.g. drawdown) hanging from a zero line,
 * filled in the down tone. Otherwise the fill runs to zero when the range spans it, else to the floor.
 * `ranges` adds range tabs (client-side slice from the last date).
 */
export function AreaChart({ points, height = 140, fmt = def, tone, underwater, ranges, label = 'area chart' }: {
  points: TPoint[];
  height?: number;
  fmt?: (v: number) => string;
  tone?: Tone;
  underwater?: boolean;
  /** Show range tabs: true for all, or a subset. */
  ranges?: boolean | readonly Range[];
  label?: string;
}) {
  const all = points.filter((p) => ok(p.v)) as { t: string; v: number }[];
  const r = useRange(all, Array.isArray(ranges) ? ranges : RANGES);
  const tabs = ranges ? r.tabs : null;
  const pts = ranges ? r.shown : all;
  if (pts.length < 2) return <div>{tabs}<p className="note mute">—</p></div>;

  const vals = pts.map((p) => p.v);
  const mn = Math.min(...vals), mx = Math.max(...vals);
  const { lo, hi } = underwater ? { lo: pad(Math.min(mn, -1e-9), 0).lo, hi: 0 } : pad(mn, mx);
  const base = Math.max(lo, Math.min(hi, 0));
  const { xf, span } = xfrac(pts.map((p) => p.t));
  const Y = (v: number) => 100 - ((v - lo) / (hi - lo)) * 100;
  const c = col[tone ?? (underwater ? 'down' : 'accent')];
  const line = pts.map((p, i) => `${(xf[i] * 100).toFixed(2)},${Y(p.v).toFixed(2)}`);
  const yb = Y(base).toFixed(2);
  const area = `${line.join(' ')} ${(xf[xf.length - 1] * 100).toFixed(2)},${yb} ${(xf[0] * 100).toFixed(2)},${yb}`;
  return (
    <div className="chart">
      {tabs}
      <div className="chart-y mono"><span>{fmt(hi)}</span><span>{fmt(lo)}</span></div>
      <Plot xf={xf} yf={(i) => Y(pts[i].v)} height={height} label={label} tip={(i) => <><b>{pts[i].t.slice(0, 10)}</b> {fmt(pts[i].v)}</>}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} aria-hidden="true">
          {[25, 50, 75].map((g) => <line key={g} x1="0" x2="100" y1={g} y2={g} stroke="var(--hair)" strokeWidth="1" vectorEffect="non-scaling-stroke" />)}
          {lo < 0 && hi > 0 ? <line x1="0" x2="100" y1={yb} y2={yb} stroke="var(--hair-strong)" strokeWidth="1" strokeDasharray="3 3" vectorEffect="non-scaling-stroke" /> : null}
          <polygon points={area} fill={c} fillOpacity="0.18" stroke="none" />
          <polyline points={line.join(' ')} fill="none" stroke={c} strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
        </svg>
      </Plot>
      <XAxis ts={pts.map((p) => p.t)} xf={xf} span={span} />
    </div>
  );
}

export type BarPt = { t: string; v: number | null | undefined };

/** Signed bar chart (up tone above zero, down tone below) with a zero line. Missing values leave a gap. */
export function BarChart({ bars, height = 120, fmt = def, label = 'bar chart' }: {
  bars: BarPt[];
  height?: number;
  fmt?: (v: number) => string;
  label?: string;
}) {
  const n = bars.length;
  const vals = bars.map((b) => b.v).filter(ok);
  if (!n || !vals.length) return <p className="note mute">—</p>;
  const { lo, hi } = pad(Math.min(0, ...vals), Math.max(0, ...vals));
  const Y = (v: number) => 100 - ((v - lo) / (hi - lo)) * 100;
  const z = Y(0);
  const w = 100 / n;
  const xf = bars.map((_, i) => (i + 0.5) / n);
  const { span } = xfrac(bars.map((b) => b.t));
  return (
    <div className="chart">
      <div className="chart-y mono"><span>{fmt(hi)}</span><span>{fmt(lo)}</span></div>
      <Plot xf={xf} yf={(i) => (ok(bars[i].v) ? Y(bars[i].v) : null)} height={height} label={label} tip={(i) => <><b>{bars[i].t.slice(0, 10)}</b> {ok(bars[i].v) ? fmt(bars[i].v) : '—'}</>}>
        <svg viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} aria-hidden="true">
          {bars.map((b, i) => {
            if (!ok(b.v)) return null;
            const y = Y(b.v);
            return <rect key={`${b.t}:${i}`} x={i * w + w * 0.15} width={w * 0.7} y={Math.min(y, z)} height={Math.max(0.3, Math.abs(y - z))} fill={b.v >= 0 ? col.up : col.down} />;
          })}
          <line x1="0" x2="100" y1={z} y2={z} stroke="var(--hair-strong)" strokeWidth="1" vectorEffect="non-scaling-stroke" />
        </svg>
      </Plot>
      <XAxis ts={bars.map((b) => b.t)} xf={xf} span={span} />
    </div>
  );
}
