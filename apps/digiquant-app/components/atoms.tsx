export type Kpi = { label: string; value: string; tone?: 'pos' | 'neg'; note?: string };

/** KPI atom: dense grid of label / figure cells. */
export function KpiGrid({ items }: { items: Kpi[] }) {
  return (
    <div className="kpis">
      {items.map((k) => (
        <div className="kpi" key={k.label}>
          <div className="kpi-l">{k.label}</div>
          <div className={`kpi-v${k.tone ? ` ${k.tone}` : ''}`}>{k.value}</div>
          {k.note ? <div className="kpi-n">{k.note}</div> : null}
        </div>
      ))}
    </div>
  );
}

/** Line atom: single series, auto-scaled, hairline stroke. Needs ≥2 points. */
export function Sparkline({ values: raw, height = 56 }: { values: (number | null | undefined)[]; height?: number }) {
  const values = (raw ?? []).filter((v): v is number => typeof v === 'number' && Number.isFinite(v));
  if (values.length < 2) return <p className="note mute">not enough points</p>;
  const lo = Math.min(...values), hi = Math.max(...values), span = hi - lo || 1;
  const pts = values.map((v, i) => `${((i / (values.length - 1)) * 100).toFixed(2)},${(100 - ((v - lo) / span) * 100).toFixed(2)}`).join(' ');
  return (
    <svg className="spark" viewBox="0 0 100 100" preserveAspectRatio="none" style={{ height }} role="img" aria-label="series">
      <polyline points={pts} fill="none" stroke="var(--accent)" strokeWidth="1.2" vectorEffect="non-scaling-stroke" />
    </svg>
  );
}

export const tone = (v: number | null | undefined): 'pos' | 'neg' | undefined => (v == null ? undefined : v >= 0 ? 'pos' : 'neg');
