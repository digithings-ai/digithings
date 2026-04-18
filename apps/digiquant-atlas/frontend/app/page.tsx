'use client';

import { useMemo } from 'react';
import { useDashboard } from '@/lib/dashboard-context';
import type { BenchmarkHistoryMap, NavChartPoint } from '@/lib/types';
import { DASHBOARD_BENCHMARK_TICKERS } from '@/lib/benchmark-tickers';
import { SUBPAGE_MAX } from '@/components/subpage-tab-bar';
import {
  TrendingUp,
  TrendingDown,
  DollarSign,
  PieChart,
  Activity,
  AlertTriangle,
  ArrowUpRight,
  Target,
  Shield,
  Zap,
  Minus,
} from 'lucide-react';
import Link from 'next/link';
import { Badge, formatPct, pnlColor } from '@/components/ui';
import {
  LineChart,
  Line,
  ResponsiveContainer,
  YAxis,
} from 'recharts';
import TopAssetsPulse from '@/components/overview/top-assets-pulse';
import AtlasLoader from '@/components/AtlasLoader';
import { computeRiskRatiosFromNavSnaps } from '@/lib/portfolio-risk-metrics';

// ─── Regime config ────────────────────────────────────────────────────────────

const REGIME_BORDER: Record<string, string> = {
  bullish: 'border-fin-green/50',
  bearish: 'border-fin-red/50',
  caution: 'border-fin-amber/50',
  neutral: 'border-fin-blue/40',
};

const REGIME_GLOW: Record<string, string> = {
  bullish: 'shadow-[0_0_60px_-12px_rgba(16,185,129,0.25)]',
  bearish: 'shadow-[0_0_60px_-12px_rgba(239,68,68,0.25)]',
  caution: 'shadow-[0_0_60px_-12px_rgba(245,158,11,0.25)]',
  neutral: 'shadow-[0_0_60px_-12px_rgba(59,130,246,0.20)]',
};

const REGIME_LABEL_COLOR: Record<string, string> = {
  bullish: 'text-fin-green',
  bearish: 'text-fin-red',
  caution: 'text-fin-amber',
  neutral: 'text-fin-blue',
};

const REGIME_BG: Record<string, string> = {
  bullish: 'bg-gradient-to-br from-fin-green/[0.08] via-transparent to-transparent',
  bearish: 'bg-gradient-to-br from-fin-red/[0.08] via-transparent to-transparent',
  caution: 'bg-gradient-to-br from-fin-amber/[0.08] via-transparent to-transparent',
  neutral: 'bg-gradient-to-br from-fin-blue/[0.07] via-transparent to-transparent',
};

const REGIME_PULSE: Record<string, string> = {
  bullish: 'bg-fin-green',
  bearish: 'bg-fin-red',
  caution: 'bg-fin-amber',
  neutral: 'bg-fin-blue',
};

const REGIME_BADGE: Record<string, 'green' | 'red' | 'amber' | 'blue'> = {
  bullish: 'green',
  bearish: 'red',
  caution: 'amber',
  neutral: 'blue',
};

/** Subtle inset wash so the overview feels regime-aware without drowning content. */
const REGIME_PAGE_AMBIENT: Record<string, string> = {
  bullish: '[box-shadow:inset_0_0_140px_-36px_rgba(16,185,129,0.16)]',
  bearish: '[box-shadow:inset_0_0_140px_-36px_rgba(239,68,68,0.16)]',
  caution: '[box-shadow:inset_0_0_140px_-36px_rgba(245,158,11,0.14)]',
  neutral: '[box-shadow:inset_0_0_140px_-36px_rgba(59,130,246,0.12)]',
};

function pickBenchmarkTicker(benchmarks: BenchmarkHistoryMap): string | null {
  for (const t of DASHBOARD_BENCHMARK_TICKERS) {
    if (benchmarks[t]?.history?.length) return t;
  }
  return null;
}

/** Inception-to-date portfolio vs first available dashboard benchmark (aligned window). */
function inceptionVsBenchmark(
  snaps: NavChartPoint[],
  benchmarks: BenchmarkHistoryMap
): { ticker: string; portPct: number; benchPct: number; excessPct: number } | null {
  const ticker = pickBenchmarkTicker(benchmarks);
  if (!ticker || snaps.length < 2) return null;
  const hist = benchmarks[ticker]?.history;
  if (!hist?.length) return null;
  const sortedBench = [...hist].sort((a, b) => a.date.localeCompare(b.date));
  const first = snaps[0];
  const last = snaps[snaps.length - 1];
  const startBench = sortedBench.find((p) => p.date >= first.date);
  const endBench = [...sortedBench].reverse().find((p) => p.date <= last.date);
  if (!startBench || !endBench || startBench.date > endBench.date) return null;
  if (last.nav <= 0 || first.nav <= 0 || startBench.price <= 0 || endBench.price <= 0) return null;
  const portPct = (last.nav / first.nav - 1) * 100;
  const benchPct = (endBench.price / startBench.price - 1) * 100;
  return { ticker, portPct, benchPct, excessPct: portPct - benchPct };
}

function thesisStatusColor(s: string): string {
  const sl = (s || '').toLowerCase();
  if (sl.includes('confirmed')) return 'text-fin-green';
  if (sl.includes('monitor') || sl.includes('watch')) return 'text-fin-amber';
  if (sl.includes('invalid') || sl.includes('broken')) return 'text-fin-red';
  return 'text-text-muted';
}
function thesisStatusDot(s: string): string {
  const sl = (s || '').toLowerCase();
  if (sl.includes('confirmed')) return 'bg-fin-green';
  if (sl.includes('monitor') || sl.includes('watch')) return 'bg-fin-amber';
  if (sl.includes('invalid') || sl.includes('broken')) return 'bg-fin-red';
  return 'bg-text-muted';
}

// ─── Mini sparkline for stat cards ───────────────────────────────────────────

function StatSparkline({ data, color }: { data: number[]; color: string }) {
  const pts = data.map((v, i) => ({ i, v }));
  return (
    <div className="h-10 w-20 shrink-0">
      <ResponsiveContainer width="100%" height="100%">
        <LineChart data={pts} margin={{ top: 2, right: 2, left: 2, bottom: 2 }}>
          <YAxis domain={['auto', 'auto']} hide width={0} />
          <Line
            type="monotone"
            dataKey="v"
            stroke={color}
            dot={false}
            strokeWidth={1.5}
            isAnimationActive={false}
          />
        </LineChart>
      </ResponsiveContainer>
    </div>
  );
}

// ─── Enhanced stat card with sparkline ───────────────────────────────────────

function StatCardEnhanced({
  label,
  value,
  valueClass = '',
  subtitle,
  icon: Icon,
  iconColor = 'text-fin-blue',
  delta,
  sparkData,
  sparkColor,
  enterStaggerIndex,
}: {
  label: string;
  value: React.ReactNode;
  valueClass?: string;
  subtitle?: string;
  icon?: React.ElementType<{ size?: number; className?: string }>;
  iconColor?: string;
  delta?: number | null;
  sparkData?: number[];
  sparkColor?: string;
  /** Stagger index for entrance animation (overview KPI strip). */
  enterStaggerIndex?: number;
}) {
  const DeltaIcon =
    delta == null ? Minus : delta > 0 ? TrendingUp : TrendingDown;
  const deltaColor = delta == null ? 'text-text-muted' : delta > 0 ? 'text-fin-green' : 'text-fin-red';

  return (
    <div
      className={`glass-card p-5 flex flex-col gap-3 hover:border-white/[0.12] transition-colors ${
        enterStaggerIndex != null ? 'animate-atlas-stat-enter' : ''
      }`}
      data-enter-delay-ms={enterStaggerIndex != null ? enterStaggerIndex * 85 : undefined}
    >
      <div className="flex items-center justify-between">
        <span className="text-[10px] font-semibold uppercase tracking-widest text-text-muted">
          {label}
        </span>
        {Icon && <Icon size={15} className={iconColor} />}
      </div>

      <div className="flex items-end justify-between gap-2">
        <div className="min-w-0">
          <div className={`text-2xl font-bold tabular-nums font-mono leading-none ${valueClass}`}>
            {value}
          </div>
          {(subtitle || delta != null) && (
            <div className="flex items-center gap-1.5 mt-1.5">
              {delta != null && (
                <span className={`flex items-center gap-0.5 text-[11px] font-mono ${deltaColor}`}>
                  <DeltaIcon size={11} />
                  {delta > 0 ? '+' : ''}{delta.toFixed(2)}%
                </span>
              )}
              {subtitle && (
                <span className="text-[11px] text-text-muted">{subtitle}</span>
              )}
            </div>
          )}
        </div>
        {sparkData && sparkData.length >= 3 && (
          <StatSparkline data={sparkData} color={sparkColor ?? '#3b82f6'} />
        )}
      </div>
    </div>
  );
}

// ─── Overview page ─────────────────────────────────────────────────────────────

export default function OverviewPage() {
  const { data, loading, error } = useDashboard();

  const benchmarkBlurb = useMemo(() => {
    if (!data?.portfolio?.snapshots?.length || !data.benchmarks) return null;
    return inceptionVsBenchmark(data.portfolio.snapshots, data.benchmarks);
  }, [data]);

  /** Align with Advanced stats / tearsheet: Sharpe from daily NAV returns (Rf = 0). */
  const overviewSharpeFromNav = useMemo(() => {
    const snaps = data?.portfolio?.snapshots;
    if (!snaps?.length) return null;
    return computeRiskRatiosFromNavSnaps(snaps)?.sharpe ?? null;
  }, [data?.portfolio?.snapshots]);

  // 7-day position activity count (non-HOLD events in last 7 calendar days from last_updated)
  const recentActivityCount = useMemo(() => {
    const events = data?.position_events ?? [];
    const anchor = data?.portfolio?.meta?.last_updated;
    if (!events.length || !anchor) return 0;
    const [y, m, d] = anchor.split('-').map(Number);
    if (!y || !m || !d) return 0;
    const cutoffDt = new Date(Date.UTC(y, m - 1, d));
    cutoffDt.setUTCDate(cutoffDt.getUTCDate() - 7);
    const cutoff = cutoffDt.toISOString().slice(0, 10);
    return events.filter((ev) => ev.event !== 'HOLD' && ev.date >= cutoff).length;
  }, [data]);

  if (loading) return <AtlasLoader />;
  if (error || !data)
    return (
      <div className="flex items-center justify-center h-screen text-fin-red">
        {error || 'Failed to load'}
      </div>
    );

  const {
    portfolio,
    positions,
    calculated: metrics,
    docs,
    snapshot_context_bullets: contextBullets,
  } = data;
  const { strategy } = portfolio;
  const regimeLabel = (strategy.regime_label || 'neutral') as string;
  const regimeBorder = REGIME_BORDER[regimeLabel] ?? REGIME_BORDER.neutral;
  const regimeGlow = REGIME_GLOW[regimeLabel] ?? REGIME_GLOW.neutral;
  const regimeLabelColor = REGIME_LABEL_COLOR[regimeLabel] ?? REGIME_LABEL_COLOR.neutral;
  const regimeBg = REGIME_BG[regimeLabel] ?? REGIME_BG.neutral;
  const regimePulse = REGIME_PULSE[regimeLabel] ?? REGIME_PULSE.neutral;
  const regimeBadgeVariant = REGIME_BADGE[regimeLabel] ?? 'blue';

  const latestDate = portfolio.meta.last_updated || null;
  const latestRunDocs = latestDate ? docs.filter((d) => d.date === latestDate) : [];
  const latestRunDocByKey = new Map(latestRunDocs.map((d) => [d.path, d]));
  const researchQuickLinks = [{ label: 'Digest', docKey: 'digest' }].filter(
    (x) => latestRunDocByKey.has(x.docKey)
  );
  const pmQuickLinks = [
    { label: 'Deliberation', keys: ['deliberation.md', 'deliberation.json'] as const },
    { label: 'Rebalance', keys: ['rebalance-decision.json'] as const },
  ].flatMap((c) => {
    const docKey = c.keys.find((k) => latestRunDocByKey.has(k));
    return docKey ? [{ label: c.label, docKey }] : [];
  });

  // NAV sparkline — last N points for the P&L stat card
  const navSnaps = portfolio.snapshots ?? [];
  const navSparkData = navSnaps.slice(-20).map((s) => s.nav);
  // Daily return
  const dailyRet =
    navSnaps.length >= 2
      ? ((navSnaps[navSnaps.length - 1].nav - navSnaps[navSnaps.length - 2].nav) /
          navSnaps[navSnaps.length - 2].nav) *
        100
      : null;


  const hasTopAssets = Object.values(data.benchmarks ?? {}).some((v) => (v?.history?.length ?? 0) >= 2);

  const pageAmbient = REGIME_PAGE_AMBIENT[regimeLabel] ?? REGIME_PAGE_AMBIENT.neutral;

  return (
    <div className={`${SUBPAGE_MAX} space-y-6 py-4 md:py-7 relative rounded-sm transition-shadow duration-500 ${pageAmbient}`}>

      {/* ── Regime Hero Banner ─────────────────────────────────────────────── */}
      <div
        className={`glass-card border ${regimeBorder} ${regimeGlow} ${regimeBg} overflow-hidden`}
      >
        <div className="px-6 pt-5 pb-6 sm:px-8 sm:pt-6">
          {/* Top row: label + badges */}
          <div className="flex flex-wrap items-center justify-between gap-3 mb-4">
            <div className="flex items-center gap-2.5">
              {/* Live pulse dot */}
              <span className="relative flex h-2.5 w-2.5 shrink-0">
                <span
                  className={`animate-ping absolute inline-flex h-full w-full rounded-full opacity-60 ${regimePulse}`}
                />
                <span className={`relative inline-flex rounded-full h-2.5 w-2.5 ${regimePulse}`} />
              </span>
              <span
                className={`text-[10px] font-bold uppercase tracking-widest ${regimeLabelColor}`}
              >
                Current regime
              </span>
            </div>
            <div className="flex items-center gap-2 flex-wrap">
              {latestDate && (
                <span className="text-[10px] text-text-muted font-mono">
                  as of {latestDate}
                </span>
              )}
              <Badge variant={regimeBadgeVariant}>
                Next review: {strategy.next_review}
              </Badge>
            </div>
          </div>

          {/* Regime name */}
          <h2 className={`text-3xl sm:text-4xl font-black tracking-tight mb-3 ${regimeLabelColor}`}>
            {strategy.regime}
          </h2>

          {/* Summary */}
          <p className="text-text-secondary leading-relaxed text-sm sm:text-base max-w-3xl">
            {strategy.summary}
          </p>

          {/* Context bullets */}
          {contextBullets.length > 0 && (
            <ul className="mt-5 space-y-1.5 border-t border-white/[0.06] pt-4">
              {contextBullets.map((b, i) => (
                <li
                  key={i}
                  className="flex items-start gap-2 text-xs text-text-muted"
                >
                  <span className={`mt-1 shrink-0 w-1 h-1 rounded-full ${regimePulse} opacity-70`} />
                  {b}
                </li>
              ))}
            </ul>
          )}
        </div>
      </div>

      {/* ── KPI Stat Strip ─────────────────────────────────────────────────── */}
      <div className="grid grid-cols-2 lg:grid-cols-4 gap-4">
        <StatCardEnhanced
          label="Portfolio P&L"
          value={formatPct(metrics.portfolio_pnl)}
          valueClass={pnlColor(metrics.portfolio_pnl)}
          icon={TrendingUp}
          iconColor="text-fin-blue"
          delta={dailyRet}
          subtitle={dailyRet != null ? 'today' : undefined}
          sparkData={navSparkData}
          sparkColor={metrics.portfolio_pnl >= 0 ? '#10b981' : '#ef4444'}
          enterStaggerIndex={0}
        />
        <StatCardEnhanced
          label="Cash reserve"
          value={`${metrics.cash_pct?.toFixed(1) ?? '—'}%`}
          icon={DollarSign}
          iconColor="text-fin-green"
          subtitle="uninvested"
          enterStaggerIndex={1}
        />
        <StatCardEnhanced
          label="Sharpe"
          value={
            overviewSharpeFromNav != null
              ? overviewSharpeFromNav.toFixed(2)
              : metrics.sharpe != null
                ? metrics.sharpe.toFixed(2)
                : '—'
          }
          icon={PieChart}
          iconColor="text-fin-amber"
          enterStaggerIndex={2}
        />
        <StatCardEnhanced
          label="Active positions"
          value={positions.length}
          icon={Activity}
          iconColor="text-fin-purple"
          subtitle={
            recentActivityCount > 0
              ? `${recentActivityCount} change${recentActivityCount !== 1 ? 's' : ''} in 7d`
              : positions.length === 1 ? 'holding' : 'holdings'
          }
          enterStaggerIndex={3}
        />
      </div>

      {/* ── Top assets (quick up/down) ─────────────────────────────────────── */}
      {hasTopAssets && <TopAssetsPulse benchmarks={data.benchmarks ?? {}} />}

      {benchmarkBlurb && (
        <div className="glass-card px-5 py-3.5 border border-border-subtle/90">
          <p className="text-sm text-text-secondary leading-relaxed">
            <span className="font-medium text-text-primary">Since inception</span>
            {' — '}portfolio{' '}
            <span className={`font-mono font-semibold tabular-nums ${pnlColor(benchmarkBlurb.portPct)}`}>
              {formatPct(benchmarkBlurb.portPct)}
            </span>
            {' vs '}
            <span className="font-mono text-text-muted">{benchmarkBlurb.ticker}</span>{' '}
            <span className={`font-mono font-semibold tabular-nums ${pnlColor(benchmarkBlurb.benchPct)}`}>
              {formatPct(benchmarkBlurb.benchPct)}
            </span>
            <span className="text-text-muted">.</span>{' '}
            <span className={`font-mono font-semibold tabular-nums ${pnlColor(benchmarkBlurb.excessPct)}`}>
              ({benchmarkBlurb.excessPct >= 0 ? '+' : ''}
              {benchmarkBlurb.excessPct.toFixed(2)}% excess)
            </span>
          </p>
        </div>
      )}

      {/* ── Main Grid: Positions | Actions+Risk ───────────────────────────── */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-5">

        {/* Left: Positions table */}
        <div className="glass-card p-0 overflow-hidden lg:col-span-1">
          <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-secondary flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Target size={15} className="text-fin-blue" />
              <h3 className="text-sm font-semibold">Positions</h3>
            </div>
            <Link
              href="/portfolio"
              className="text-[10px] text-fin-blue hover:underline font-medium"
            >
              View all →
            </Link>
          </div>
          <div className="divide-y divide-border-subtle">
            {positions.slice(0, 10).map((p, i) => (
              <div
                key={i}
                className="flex items-center justify-between px-5 py-2.5 hover:bg-white/[0.025] transition-colors"
              >
                <div className="flex items-center gap-2.5 min-w-0">
                  <span className="font-mono text-xs font-bold text-fin-blue shrink-0 w-12">
                    {p.ticker}
                  </span>
                  <span className="text-xs text-text-secondary truncate">{p.name}</span>
                </div>
                <div className="text-right shrink-0 min-w-[56px]">
                  <span className="text-xs font-mono font-semibold tabular-nums">
                    {p.weight_actual?.toFixed(1)}%
                  </span>
                  {typeof p.weight_delta === 'number' && p.weight_delta !== 0 && (
                    <div
                      className={`text-[10px] font-mono tabular-nums ${
                        p.weight_delta > 0 ? 'text-fin-green' : 'text-fin-red'
                      }`}
                    >
                      {p.weight_delta > 0 ? '+' : ''}
                      {p.weight_delta.toFixed(1)}pp
                    </div>
                  )}
                </div>
              </div>
            ))}
            {positions.length === 0 && (
              <p className="text-center py-10 text-text-muted text-sm">
                No active positions
              </p>
            )}
            {positions.length > 10 && (
              <div className="px-5 py-2.5 text-center">
                <Link
                  href="/portfolio"
                  className="text-xs text-fin-blue hover:underline"
                >
                  +{positions.length - 10} more positions
                </Link>
              </div>
            )}
          </div>
        </div>

        {/* Center: Actionable + Risk + Quick Links */}
        <div className="lg:col-span-1 flex flex-col gap-4">

          {/* (Removed) Latest run quick links block */}

          {/* Actionable summary */}
          <div className="glass-card p-5 flex-1">
            <div className="flex items-center gap-2 mb-3">
              <Zap size={14} className="text-fin-green shrink-0" />
              <h3 className="text-sm font-semibold">Actionable</h3>
            </div>
            <ul className="space-y-2.5">
              {strategy.actionable?.length > 0 ? (
                strategy.actionable.map((a, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm text-text-secondary">
                    <span className="mt-1 shrink-0 w-4 h-4 rounded-full bg-fin-green/15 border border-fin-green/30 flex items-center justify-center">
                      <ArrowUpRight size={9} className="text-fin-green" />
                    </span>
                    {a}
                  </li>
                ))
              ) : (
                <li className="text-text-muted text-sm">No actionable items.</li>
              )}
            </ul>
          </div>

          {/* Risk radar */}
          <div className="glass-card p-5 bg-gradient-to-b from-fin-red/[0.04] to-transparent">
            <div className="flex items-center gap-2 mb-3">
              <AlertTriangle size={14} className="text-fin-red shrink-0" />
              <h3 className="text-sm font-semibold">Risk radar</h3>
            </div>
            <ul className="space-y-2.5">
              {strategy.risks?.length > 0 ? (
                strategy.risks.map((r, i) => (
                  <li key={i} className="flex items-start gap-2.5 text-sm">
                    <span className="mt-1 shrink-0 w-4 h-4 rounded-full bg-fin-red/15 border border-fin-red/30 flex items-center justify-center">
                      <AlertTriangle size={8} className="text-fin-red" />
                    </span>
                    <span className="text-red-300/90">{r}</span>
                  </li>
                ))
              ) : (
                <li className="text-text-muted text-sm">No immediate risks flagged.</li>
              )}
            </ul>
          </div>
        </div>
      </div>

      {/* ── Thesis Table ───────────────────────────────────────────────────── */}
      {strategy.theses?.length > 0 && (
        <div className="glass-card p-0 overflow-hidden">
          <div className="px-5 py-3.5 border-b border-border-subtle bg-bg-secondary flex items-center justify-between">
            <div className="flex items-center gap-2">
              <Shield size={15} className="text-fin-amber" />
              <h3 className="text-sm font-semibold">Active theses</h3>
            </div>
            <Link
              href="/portfolio?tab=analysis"
              className="text-[10px] text-fin-amber hover:underline font-medium"
            >
              Full tracker →
            </Link>
          </div>
          <div className="overflow-x-auto">
            <table className="w-full text-sm">
              <thead>
                <tr className="border-b border-border-subtle text-[10px] uppercase tracking-widest text-text-muted">
                  <th className="px-5 py-3 text-left w-8" aria-label="Status" />
                  <th className="px-5 py-3 text-left">ID</th>
                  <th className="px-5 py-3 text-left">Thesis</th>
                  <th className="hidden px-5 py-3 text-left sm:table-cell">Vehicle</th>
                  <th className="px-5 py-3 text-left">Status</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-border-subtle">
                {strategy.theses.map((t, i) => (
                  <tr key={i} className="hover:bg-white/[0.02] transition-colors">
                    <td className="px-5 py-3">
                      <span
                        className={`block w-2 h-2 rounded-full ${thesisStatusDot(t.status ?? '')}`}
                      />
                    </td>
                    <td className="px-5 py-3 font-mono text-xs">
                      <Link
                        href={`/portfolio/theses/${encodeURIComponent(t.id)}`}
                        className="text-fin-blue hover:underline"
                      >
                        {t.id}
                      </Link>
                    </td>
                    <td className="px-5 py-3 font-medium max-w-[220px]">
                      <span className="line-clamp-1">{t.name}</span>
                    </td>
                    <td className="hidden px-5 py-3 font-mono text-xs text-text-secondary sm:table-cell">
                      {t.vehicle}
                    </td>
                    <td className={`px-5 py-3 text-xs font-semibold ${thesisStatusColor(t.status ?? '')}`}>
                      {t.status}
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        </div>
      )}

      {/* ── Footer: Architecture link ──────────────────────────────────────── */}
      <p className="text-center text-xs text-text-muted pb-2">
        <Link
          href="/architecture"
          className="text-fin-blue/70 hover:text-fin-blue hover:underline"
        >
          How Atlas works →
        </Link>
      </p>
    </div>
  );
}
