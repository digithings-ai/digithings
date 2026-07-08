'use client';

import Link from 'next/link';
import type { ElementType } from 'react';
import { BookOpen, Wallet, Shield } from 'lucide-react';
import { buildPipelineHref } from '@/lib/pipeline-links';

/**
 * The three quiet "doorway" cards beneath the hero. Each is a scannable summary
 * that links into a deep surface — never full visual weight, so the read stays
 * the focal element on the page. The performance doorway is retired until a
 * meaningful time-series exists.
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
  positions: TodayHolding[];
  theses: TodayThesis[];
  /** The digest headline (`strategy.summary`) — the read doorway's teaser. */
  readSummary: string | null;
  /** Run date — keys the read doorway's Pipeline deep-link (F2). */
  asOfDate: string | null;
}

function statusDot(s: string): string {
  const sl = (s || '').toLowerCase();
  if (sl.includes('confirmed')) return 'bg-up';
  if (sl.includes('monitor') || sl.includes('watch')) return 'bg-warn';
  if (sl.includes('invalid') || sl.includes('broken')) return 'bg-down';
  return 'bg-ink-mute';
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
      className="glass-card block p-4 transition-colors hover:border-hair-2"
    >
      <div className="mb-2.5 flex items-center justify-between gap-2">
        <div className="flex items-center gap-2">
          <Icon size={14} className="text-ink-mute" />
          <h3 className="text-xs font-bold uppercase tracking-widest text-ink-mute">{title}</h3>
        </div>
        <span className="text-[10px] font-medium text-accent">{cta} →</span>
      </div>
      {children}
    </Link>
  );
}

export function TodaySummaries({
  positions,
  theses,
  readSummary,
  asOfDate,
}: TodaySummariesProps) {
  return (
    <div className="grid grid-cols-1 gap-4 sm:grid-cols-3">
      {/* The read */}
      <Doorway
        title="The read"
        cta="Read"
        href={buildPipelineHref({ date: asOfDate, stage: 'synthesis', node: 'digest' })}
        icon={BookOpen}
      >
        <p className="line-clamp-3 text-sm leading-snug text-ink-soft">
          {readSummary ?? 'The latest research digest will appear here after the next run.'}
        </p>
      </Doorway>

      {/* Holdings */}
      <Doorway title="Holdings" cta="All holdings" href="/portfolio" icon={Wallet}>
        {positions.length === 0 ? (
          <p className="text-sm text-ink-mute">No positions yet.</p>
        ) : (
          <ul className="space-y-1">
            {positions.slice(0, 6).map((p, i) => (
              <li key={`${p.ticker}-${i}`} className="flex items-center justify-between gap-2 text-xs">
                <span className="font-mono font-semibold text-ink">{p.ticker}</span>
                <span className="flex items-center gap-2 font-mono tabular-nums">
                  <span className="text-ink-soft">{(p.weight_actual ?? 0).toFixed(1)}%</span>
                  {typeof p.weight_delta === 'number' && p.weight_delta !== 0 ? (
                    <span className={p.weight_delta > 0 ? 'text-up' : 'text-down'}>
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
          <p className="text-sm text-ink-mute">No active theses yet.</p>
        ) : (
          <ul className="space-y-1.5">
            {theses.slice(0, 5).map((t, i) => (
              <li key={`${t.id}-${i}`} className="flex items-center gap-2 text-xs">
                <span className={`h-2 w-2 shrink-0 rounded-full ${statusDot(t.status ?? '')}`} />
                <span className="truncate text-ink-soft">{t.name}</span>
              </li>
            ))}
          </ul>
        )}
      </Doorway>
    </div>
  );
}
