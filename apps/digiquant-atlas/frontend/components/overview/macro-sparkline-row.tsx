'use client';

import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts';
import type { MacroSeriesPoint } from '@/lib/types';

const LABELS: Record<string, string> = {
  VIXCLS: 'VIX',
  DGS10: '10Y Yield',
  DEXUSEU: 'USD/EUR',
  DTWEXBGS: 'DXY',
  DFF: 'Fed Funds',
  T10YIE: '10Y Breakeven',
};

const UNITS: Record<string, string> = {
  DGS10: '%',
  DFF: '%',
  T10YIE: '%',
  VIXCLS: '',
  DEXUSEU: '',
  DTWEXBGS: '',
};

function fmt(v: number | null, sid: string): string {
  if (v == null) return '—';
  const dec = ['DGS10', 'DFF', 'T10YIE', 'DEXUSEU'].includes(sid) ? 2 : 1;
  const unit = UNITS[sid] ?? '';
  return `${v.toFixed(dec)}${unit}`;
}

export default function MacroSparklineRow({
  series,
}: {
  series: Record<string, MacroSeriesPoint[]>;
}) {
  const ids = Object.keys(series).filter((k) => (series[k]?.length ?? 0) >= 2);
  if (ids.length === 0) return null;

  return (
    <div className="glass-card px-5 py-5">
      <p className="text-[10px] text-text-muted uppercase tracking-widest mb-4 flex items-center gap-2">
        <span className="inline-block w-1.5 h-1.5 rounded-full bg-fin-blue animate-pulse" />
        Macro pulse
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 lg:grid-cols-4 gap-x-6 gap-y-4">
        {ids.slice(0, 8).map((sid) => {
          const pts = series[sid];
          const data = pts.map((p) => ({ x: p.obs_date, y: p.value }));
          const latest = pts[pts.length - 1]?.value ?? null;
          const prev = pts[pts.length - 2]?.value ?? null;
          const delta = latest != null && prev != null ? latest - prev : null;
          const up = delta != null && delta >= 0;
          const changeColor = delta == null ? 'text-text-muted' : up ? 'text-fin-green' : 'text-fin-red';
          const lineColor = delta == null ? '#60a5fa' : up ? '#10b981' : '#ef4444';

          return (
            <div key={sid} className="min-w-0">
              <div className="flex items-baseline justify-between gap-1 mb-1">
                <p className="text-[10px] font-semibold text-text-muted uppercase tracking-wider truncate">
                  {LABELS[sid] ?? sid}
                </p>
                <div className="flex items-baseline gap-1 shrink-0">
                  <span className="text-sm font-bold font-mono tabular-nums text-text-primary">
                    {fmt(latest, sid)}
                  </span>
                  {delta != null && (
                    <span className={`text-[10px] font-mono tabular-nums ${changeColor}`}>
                      {delta > 0 ? '+' : ''}{delta.toFixed(['DGS10','DFF','T10YIE','DEXUSEU'].includes(sid) ? 2 : 1)}
                    </span>
                  )}
                </div>
              </div>
              <div className="h-16 w-full">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={data} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
                    <YAxis domain={['auto', 'auto']} hide width={0} />
                    <Line
                      type="monotone"
                      dataKey="y"
                      stroke={lineColor}
                      dot={false}
                      strokeWidth={1.5}
                      isAnimationActive={false}
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            </div>
          );
        })}
      </div>
    </div>
  );
}
