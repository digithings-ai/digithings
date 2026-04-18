 'use client';
 
import { useCallback, useMemo, useRef } from 'react';
import { Line, LineChart, ResponsiveContainer, YAxis } from 'recharts';
import type { BenchmarkHistoryMap } from '@/lib/types';
import { ChevronLeft, ChevronRight } from 'lucide-react';
 
const PREFERRED_ORDER: string[] = [
  'SPY',
  'QQQ',
  'DIA',
  'IWM',
  'VTI',
  'EEM',
  'TLT',
  'IEF',
  'AGG',
  'HYG',
  'GLD',
  'SLV',
  'USO',
  'UUP',
  'IBIT',
  'BITO',
];

const LABELS: Record<string, string> = {
  SPY: 'S&P 500',
  QQQ: 'Nasdaq 100',
  DIA: 'Dow',
  IWM: 'Russell 2000',
  VTI: 'Total US',
  EEM: 'EM',
  TLT: '20Y UST',
  IEF: '10Y UST',
  AGG: 'Agg bonds',
  HYG: 'High yield',
  GLD: 'Gold',
  SLV: 'Silver',
  USO: 'Oil',
  UUP: 'DXY proxy',
  IBIT: 'Bitcoin',
  BITO: 'BTC futures',
};
 
 function fmt(v: number | null | undefined): string {
   if (v == null || Number.isNaN(v)) return '—';
   return v >= 100 ? v.toFixed(0) : v >= 10 ? v.toFixed(1) : v.toFixed(2);
 }
 
export default function TopAssetsPulse({ benchmarks }: { benchmarks: BenchmarkHistoryMap }) {
  const availableTickers = Object.keys(benchmarks ?? {}).map((t) => String(t).toUpperCase());
  const order = [
    ...PREFERRED_ORDER.filter((t) => availableTickers.includes(t)),
    ...availableTickers.filter((t) => !PREFERRED_ORDER.includes(t)).sort(),
  ];

  const items = order.flatMap((t) => {
    const b = benchmarks[t];
    if (!b?.history?.length || b.history.length < 2) return [];
    return [{ ticker: t, history: b.history }];
  });

  const scrollerRef = useRef<HTMLDivElement | null>(null);
  const scrollByTiles = useCallback((dir: -1 | 1) => {
    const el = scrollerRef.current;
    if (!el) return;
    const maxScroll = el.scrollWidth - el.clientWidth;
    if (maxScroll <= 0) return;

    const amt = Math.min(720, Math.max(280, Math.round(el.clientWidth * 0.85)));
    const eps = 3;

    if (dir === 1) {
      if (el.scrollLeft >= maxScroll - eps) {
        el.scrollTo({ left: 0, behavior: 'smooth' });
      } else {
        el.scrollBy({ left: amt, behavior: 'smooth' });
      }
    } else {
      if (el.scrollLeft <= eps) {
        el.scrollTo({ left: maxScroll, behavior: 'smooth' });
      } else {
        el.scrollBy({ left: -amt, behavior: 'smooth' });
      }
    }
  }, []);

  if (items.length === 0) return null;

  const canScroll = items.length > 3;
 
  return (
    <div className="relative group">
      {canScroll && (
        <>
          <button
            type="button"
            onClick={() => scrollByTiles(-1)}
            className="absolute left-0 top-1/2 -translate-y-1/2 z-10 hidden sm:grid place-items-center h-10 w-10 rounded-full border border-border-subtle bg-bg-glass/90 backdrop-blur opacity-0 pointer-events-none transition-opacity duration-200 sm:group-hover:opacity-100 sm:group-hover:pointer-events-auto hover:bg-white/[0.06]"
            aria-label="Scroll left (loops to end)"
          >
            <ChevronLeft size={18} className="text-text-secondary" />
          </button>
          <button
            type="button"
            onClick={() => scrollByTiles(1)}
            className="absolute right-0 top-1/2 -translate-y-1/2 z-10 hidden sm:grid place-items-center h-10 w-10 rounded-full border border-border-subtle bg-bg-glass/90 backdrop-blur opacity-0 pointer-events-none transition-opacity duration-200 sm:group-hover:opacity-100 sm:group-hover:pointer-events-auto hover:bg-white/[0.06]"
            aria-label="Scroll right (loops to start)"
          >
            <ChevronRight size={18} className="text-text-secondary" />
          </button>
        </>
      )}

      <div
        ref={scrollerRef}
        className="overflow-x-auto scroll-smooth [-ms-overflow-style:none] [scrollbar-width:none] [&::-webkit-scrollbar]:hidden"
      >
        <div className="flex gap-4 min-w-max pb-2 pr-1">
          {items.map(({ ticker, history }) => {
           const latest = history[history.length - 1]?.price ?? null;
           const prev = history[history.length - 2]?.price ?? null;
           const delta = latest != null && prev != null ? latest - prev : null;
           const pct = latest != null && prev != null && prev !== 0 ? ((latest / prev) - 1) * 100 : null;
           const up = delta != null && delta >= 0;
           const changeColor =
             delta == null ? 'text-text-muted' : up ? 'text-fin-green' : 'text-fin-red';
           const lineColor = delta == null ? '#60a5fa' : up ? '#10b981' : '#ef4444';
           const data = history.map((p) => ({ x: p.date, y: p.price }));
 
           return (
             <div
               key={ticker}
                className="w-[220px] shrink-0 rounded-2xl bg-bg-secondary/40 px-4 py-3 shadow-[0_16px_44px_-30px_rgba(0,0,0,0.85)] ring-1 ring-white/[0.06] hover:ring-white/[0.10] hover:bg-white/[0.03] transition-colors"
             >
               <div className="flex items-baseline justify-between gap-2 mb-1">
                  <p className="text-[11px] font-semibold text-text-secondary uppercase tracking-wider truncate">
                    {ticker}
                  </p>
                 <div className="flex items-baseline gap-1.5 shrink-0">
                   <span className="text-sm font-bold font-mono tabular-nums text-text-primary">
                     {fmt(latest)}
                   </span>
                   {pct != null && (
                     <span className={`text-[10px] font-mono tabular-nums ${changeColor}`}>
                       {pct > 0 ? '+' : ''}
                       {pct.toFixed(2)}%
                     </span>
                   )}
                 </div>
               </div>
                <p className="text-[10px] text-text-muted -mt-0.5 mb-2 truncate">{LABELS[ticker] ?? ''}</p>
 
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
    </div>
  );
 }

