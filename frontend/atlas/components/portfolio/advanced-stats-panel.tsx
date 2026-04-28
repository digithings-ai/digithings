'use client';

import { useMemo } from 'react';
import type { BenchmarkHistoryMap, NavChartPoint } from '@/lib/types';
import {
  dailySimpleReturnsFromNavs,
  sharpeRatioFromDailyReturns,
  sortinoRatioFromDailyReturns,
  annualizedVolatilityPctFromDailyReturns,
} from '@/lib/portfolio-risk-metrics';

interface MetricProps {
  label: string;
  value: number | string | null | undefined;
  fmt?: (v: number) => string;
  color?: string;
  sub?: string;
}

function MetricCard({ label, value, fmt, color, sub }: MetricProps) {
  return (
    <div className="bg-bg-secondary rounded-lg p-4 border border-border-subtle">
      <span className="text-xs text-text-muted block mb-1">{label}</span>
      <span className={`text-lg font-bold tabular-nums ${color || ''}`}>
        {fmt && value != null ? fmt(value as number) : value}
      </span>
      {sub && <span className="text-xs text-text-muted block mt-1">{sub}</span>}
    </div>
  );
}

interface ComputedStats {
  tradingDays: number;
  totalReturn: number;
  annReturn: number;
  annVol: number;
  sharpe: number;
  sortino: number;
  maxDd: number;
  ddStart: string;
  ddEnd: string;
  currDd: number;
  winRate: number;
  upDays: number;
  downDays: number;
  avgWin: number;
  avgLoss: number;
  profitFactor: number;
  calmar: number;
  bestDay: number;
  worstDay: number;
  beta: number | null;
  correlation: number | null;
  alphaAnn: number | null;
  trackingError: number | null;
  infoRatio: number | null;
}

export function AdvancedStatsPanel({
  snaps,
  benchmarks,
}: {
  snaps: NavChartPoint[];
  benchmarks: BenchmarkHistoryMap;
}) {
  const stats = useMemo<ComputedStats | null>(() => {
    if (!snaps || snaps.length < 2) return null;

    const navs: number[] = snaps.map((s) => s.nav);
    const returns = dailySimpleReturnsFromNavs(navs);
    if (!returns.length) return null;

    const tradingDays = returns.length;
    const firstNav = navs[0];
    const lastNav = navs[navs.length - 1];
    const totalReturn = (lastNav / firstNav - 1) * 100;
    const annFactor = tradingDays > 0 ? 252 / tradingDays : 1;
    const annReturn = ((1 + totalReturn / 100) ** annFactor - 1) * 100;

    const annVol = annualizedVolatilityPctFromDailyReturns(returns);
    const sharpe = sharpeRatioFromDailyReturns(returns);
    const sortino = sortinoRatioFromDailyReturns(returns);

    const downReturns = returns.filter((r) => r < 0);

    let peak = firstNav;
    let maxDd = 0;
    let ddStart = snaps[0].date;
    let ddEnd = snaps[0].date;
    let tempStart = snaps[0].date;
    for (let i = 0; i < navs.length; i++) {
      const nav = navs[i];
      if (nav > peak) {
        peak = nav;
        tempStart = snaps[i].date;
      }
      const dd = (nav - peak) / peak;
      if (dd < maxDd) {
        maxDd = dd;
        ddStart = tempStart;
        ddEnd = snaps[i].date;
      }
    }

    const upDays = returns.filter((r) => r > 0).length;
    const downDays = returns.filter((r) => r < 0).length;
    const winRate = tradingDays > 0 ? (upDays / tradingDays) * 100 : 0;
    const avgWin =
      upDays > 0 ? (returns.filter((r) => r > 0).reduce((a, b) => a + b, 0) / upDays) * 100 : 0;
    const avgLoss =
      downDays > 0 ? (downReturns.reduce((a, b) => a + b, 0) / downDays) * 100 : 0;
    const profitFactor = avgLoss !== 0 ? Math.abs((avgWin * upDays) / (avgLoss * downDays)) : 0;

    const calmar = maxDd !== 0 ? annReturn / (Math.abs(maxDd) * 100) : 0;
    const bestDay = Math.max(...returns) * 100;
    const worstDay = Math.min(...returns) * 100;
    const currDd = peak > 0 ? ((lastNav - peak) / peak) * 100 : 0;

    let beta: number | null = null;
    let correlation: number | null = null;
    let alphaAnn: number | null = null;
    let trackingError: number | null = null;
    let infoRatio: number | null = null;

    const spyHist = benchmarks?.SPY?.history || [];
    if (spyHist.length > 1) {
      const spyMap: Record<string, number> = {};
      spyHist.forEach((h) => {
        spyMap[h.date] = h.price;
      });
      const pairedReturns: { port: number; spy: number }[] = [];
      for (let i = 1; i < snaps.length; i++) {
        const d = snaps[i].date;
        const dPrev = snaps[i - 1].date;
        const currNav = navs[i];
        const prevNav = navs[i - 1];
        if (spyMap[d] != null && spyMap[dPrev] != null && spyMap[dPrev] > 0 && prevNav > 0) {
          pairedReturns.push({
            port: (currNav - prevNav) / prevNav,
            spy: (spyMap[d] - spyMap[dPrev]) / spyMap[dPrev],
          });
        }
      }
      if (pairedReturns.length > 5) {
        const pMean = pairedReturns.reduce((a, b) => a + b.port, 0) / pairedReturns.length;
        const sMean = pairedReturns.reduce((a, b) => a + b.spy, 0) / pairedReturns.length;
        let cov = 0;
        let sVar = 0;
        pairedReturns.forEach((r) => {
          cov += (r.port - pMean) * (r.spy - sMean);
          sVar += (r.spy - sMean) ** 2;
        });
        cov /= pairedReturns.length;
        sVar /= pairedReturns.length;
        beta = sVar > 0 ? cov / sVar : 0;

        const pStd = Math.sqrt(
          pairedReturns.reduce((a, b) => a + (b.port - pMean) ** 2, 0) / pairedReturns.length
        );
        const sStd = Math.sqrt(sVar);
        correlation = pStd > 0 && sStd > 0 ? cov / (pStd * sStd) : 0;
        alphaAnn = (pMean * 252 - beta * sMean * 252) * 100;

        const diffs = pairedReturns.map((r) => r.port - r.spy);
        const diffMean = diffs.reduce((a, b) => a + b, 0) / diffs.length;
        const diffVar = diffs.reduce((s, d) => s + (d - diffMean) ** 2, 0) / diffs.length;
        trackingError = Math.sqrt(diffVar) * Math.sqrt(252) * 100;
        infoRatio = trackingError > 0 ? (diffMean * 252 * 100) / trackingError : 0;
      }
    }

    return {
      tradingDays,
      totalReturn,
      annReturn,
      annVol,
      sharpe,
      sortino,
      maxDd: maxDd * 100,
      ddStart,
      ddEnd,
      currDd,
      winRate,
      upDays,
      downDays,
      avgWin,
      avgLoss,
      profitFactor,
      calmar,
      bestDay,
      worstDay,
      beta,
      correlation,
      alphaAnn,
      trackingError,
      infoRatio,
    };
  }, [snaps, benchmarks]);

  if (!stats) {
    return (
      <div className="px-6 py-8 text-center text-text-muted text-sm">
        Insufficient data for advanced statistics
      </div>
    );
  }

  const fPct = (v: number) => (v != null ? `${v >= 0 ? '+' : ''}${v.toFixed(2)}%` : '—');
  const fNum = (v: number) => (v != null ? v.toFixed(2) : '—');
  const pcol = (v: number | null | undefined) =>
    v != null ? (v >= 0 ? 'text-fin-green' : 'text-fin-red') : '';

  return (
    <div className="px-6 pb-6 space-y-6">
      <div>
        <h4 className="text-sm font-semibold text-text-secondary mb-3">Returns</h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard
            label="Total Return"
            value={stats.totalReturn}
            fmt={fPct}
            color={pcol(stats.totalReturn)}
          />
          <MetricCard
            label="Annualized Return"
            value={stats.annReturn}
            fmt={fPct}
            color={pcol(stats.annReturn)}
          />
          <MetricCard label="Best Day" value={stats.bestDay} fmt={fPct} color="text-fin-green" />
          <MetricCard label="Worst Day" value={stats.worstDay} fmt={fPct} color="text-fin-red" />
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-text-secondary mb-3">
          Risk
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="Ann. Volatility" value={stats.annVol} fmt={fPct} />
          <MetricCard
            label="Max Drawdown"
            value={stats.maxDd}
            fmt={fPct}
            color="text-fin-red"
            sub={`${stats.ddStart} → ${stats.ddEnd}`}
          />
          <MetricCard
            label="Current Drawdown"
            value={stats.currDd}
            fmt={fPct}
            color={pcol(stats.currDd)}
          />
          <MetricCard label="Trading Days" value={stats.tradingDays} />
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-text-secondary mb-3">
          Risk-Adjusted
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="Sharpe Ratio" value={stats.sharpe} fmt={fNum} sub="Rf = 0%" />
          <MetricCard label="Sortino Ratio" value={stats.sortino} fmt={fNum} sub="Downside deviation" />
          <MetricCard label="Calmar Ratio" value={stats.calmar} fmt={fNum} sub="Return / MaxDD" />
          <MetricCard label="Profit Factor" value={stats.profitFactor} fmt={fNum} />
        </div>
      </div>

      <div>
        <h4 className="text-sm font-semibold text-text-secondary mb-3">
          Win / Loss
        </h4>
        <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
          <MetricCard label="Win Rate" value={stats.winRate} fmt={fPct} />
          <MetricCard label="Up Days" value={stats.upDays} />
          <MetricCard label="Avg Win" value={stats.avgWin} fmt={fPct} color="text-fin-green" />
          <MetricCard label="Avg Loss" value={stats.avgLoss} fmt={fPct} color="text-fin-red" />
        </div>
      </div>

      {stats.beta != null && (
        <div>
          <h4 className="text-sm font-semibold text-text-secondary mb-3">
            vs SPY
          </h4>
          <div className="grid grid-cols-2 md:grid-cols-4 gap-3">
            <MetricCard label="Beta" value={stats.beta} fmt={fNum} />
            <MetricCard label="Correlation" value={stats.correlation} fmt={fNum} />
            <MetricCard
              label="Alpha (ann.)"
              value={stats.alphaAnn}
              fmt={fPct}
              color={pcol(stats.alphaAnn)}
            />
            <MetricCard
              label="Info Ratio"
              value={stats.infoRatio}
              fmt={fNum}
              sub={`TE: ${stats.trackingError?.toFixed(2)}%`}
            />
          </div>
        </div>
      )}
    </div>
  );
}
