'use client';

import Link from 'next/link';
import type { ElementType } from 'react';
import { LineChart, Line, ResponsiveContainer, YAxis } from 'recharts';
import { TrendingUp, BookOpen, Wallet, Shield } from 'lucide-react';

/**
 * The four quiet "doorway" cards beneath the hero. Each is a scannable summary
 * that links into a deep surface — never full visual weight, so the move stays
 * the only focal element on the page.
 */

export interface TodayHolding {
  ticker: string;
  name?: string | null;
  weight_actual?: number | null;
  weight_delta?: number | null;
}

export interface TodayThesis {
  id: string;
  name: string;
  status?: string | null;
}

export interface TodaySummariesProps {
  navSpark: number[];
  excessPct: number | null;
  sharpe: number | null;
  positions: TodayHolding[];
  theses: TodayThesis[];
  /** The digest headline (`strategy.summary`) — the read doorway's teaser. */
  readSummary: string | null;
}

function Sparkline({ data }: { data: number[] }) {
  if (data.length < 3) return null;
  const pts = data.map((v, i) => ({ i, v }));
  const up = data[data.length - 1] >= data[0];
  return (
    <div className="h-9 w-24 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={pts} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <YAxis domain={['auto', 'auto']} hide width={0} />
          <Line
            type="monotone"
            dataKey="v"
            stroke={up ? 'var(--up)' : 'var(--down)'}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

function statusDot(s: string): string {
  const sl = (s || '').toLowerCase();
  if (sl.includes('confirmed')) return 'bg-fin-green';
  if (sl.includes('monitor') || sl.includes('watch')) return 'bg-fin-amber';
  if (sl.includes('invalid') || sl.includes('broken')) return 'bg-fin-red';
  return 'bg-text-muted';
}

function Doorway({
  title,
  cta,
  href,
  icon: Icon,
  children,
}: {
  title: string;
  cta: string;
  href: string;
  icon: ElementType<{ size?: number; className?: string }>;
  children: React.ReactNode;
}) {
  return (
    <Link
      href={href}
      className="glass-card block p-4 transition-colors hover:border-white/[0.12]"
    >
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon size={14} className="text-text-muted" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-text-muted">{title}</h3>
        </div>
        <span className="text-[10px] font-medium text-fin-blue">{cta} →</span>
      </div>
      {children}
    </Link>
  );
}

export function TodaySummaries({
  navSpark,
  excessPct,
  sharpe,
  positions,
  theses,
  readSummary,
}: TodaySummariesProps) {
  const excessColor =
    excessPct == null ? 'text-text-muted' : excessPct >= 0 ? 'text-fin-green' : 'text-fin-red';

  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-2">
      {/* How I'm doing */}
      <Doorway title={"How I'm doing"} cta="Performance" href="/portfolio?tab=performance" icon={TrendingUp}>
        <div className="flex items-end justify-between gap-3">
          <div className="font-mono text-sm tabular-nums">
            <div className={excessColor}>
              {excessPct == null ? '—' : `${excessPct > 0 ? '+' : ''}${excessPct.toFixed(1)}%`}
              <span className="ml-1 text-[11px] text-text-muted">excess</span>
            </div>
            <div className="mt-0.5 text-text-secondary">
              Sharpe <span className="text-text-primary">{sharpe == null ? '—' : sharpe.toFixed(2)}</span>
            </div>
          </div>
          <Sparkline data={navSpark} />
        </div>
      </Doorway>

      {/* The read */}
      <Doorway title="The read" cta="Read" href="/why" icon={BookOpen}>
        <p className="line-clamp-3 text-sm leading-snug text-text-secondary">
          {readSummary ?? 'The latest research digest will appear here after the next run.'}
        </p>
      </Doorway>

      {/* Holdings */}
      <Doorway title="Holdings" cta="All holdings" href="/portfolio" icon={Wallet}>
        {positions.length === 0 ? (
          <p className="text-sm text-text-muted">No positions yet.</p>
        ) : (
          <ul className="space-y-1">
            {positions.slice(0, 6).map((p, i) => (
              <li key={`${p.ticker}-${i}`} className="flex items-center justify-between gap-2 text-xs">
                <span className="font-mono font-semibold text-text-primary">{p.ticker}</span>
                <span className="flex items-center gap-2 font-mono tabular-nums">
                  <span className="text-text-secondary">{(p.weight_actual ?? 0).toFixed(1)}%</span>
                  {typeof p.weight_delta === 'number' && p.weight_delta !== 0 ? (
                    <span className={p.weight_delta > 0 ? 'text-fin-green' : 'text-fin-red'}>
                      {p.weight_delta > 0 ? '+' : ''}
                      {p.weight_delta.toFixed(1)}pp
                    </span>
                  ) : null}
                </span>
              </li>
            ))}
          </ul>
        )}
      </Doorway>

      {/* Theses */}
      <Doorway title="Theses" cta="Tracker" href="/portfolio?tab=theses" icon={Shield}>
        {theses.length === 0 ? (
          <p className="text-sm text-text-muted">No active theses yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {theses.slice(0, 5).map((t, i) => (
              <li key={`${t.id}-${i}`} className="flex items-center gap-2 text-xs">
                <span className={`h-2 w-2 shrink-0 rounded-full ${statusDot(t.status ?? '')}`} />
                <span className="truncate text-text-secondary">{t.name}</span>
              </li>
            ))}
          </ul>
        )}
      </Doorway>
    </div>
  );
}
