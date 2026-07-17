"use client";
/**
 * OlympusPortfolioPanel (#1461/#1462) — the payoff under the Olympus pipeline
 * scrolly: the research book, valued live off the same feed. A client island
 * on useLivePortfolio.
 *
 * Reuse over reinvention (digiweb canon): the at-a-glance headline / ratios /
 * weight bars are the shared @digithings/web <PerformanceDashboard/>, and the
 * "live research portfolio" mark is the shared <LiveBadge/>. Only the
 * per-position blotter is a local table — SortableTable tones a whole column,
 * but each leg carries its own sign, so per-row money colors need per-cell
 * tone (the same call olympus's AllocationsPositionsTable documents in
 * lib/TABLES.md). Money colors (--up/--down via text-up/text-down) mark P&L
 * direction only; weight bars wear the module accent (a share, not a return).
 *
 * Data facts this markup is built on (verified against the live views + the
 * writer, digiquant/src/digiquant/olympus/hermes/portfolio_materialize.py):
 *   - NAV is a base-100 normalized paper index (that file: "NAV is a base-100
 *     normalized index", _SEED_NAV = 100.0). Inception is 100, seeded the day
 *     before the first stored row — which is why that row's day return is null.
 *     So the headline is a level and "since inception" = level − 100.
 *   - weight_pct / cash_pct / invested_pct are 0–100; every *_pct return is in
 *     percent points; metrics_as_of is a YYYY-MM-DD string.
 *   - Today's book is macro ETFs (no crypto legs), so the live lane ticks only
 *     during US market hours via the equity broadcast; otherwise every leg
 *     falls back to its last close (isLive=false) and the book reads flat.
 *
 * Liveness is gated on the feed, never on mere presence: the surface LiveBadge
 * shows when the feed is configured, per-leg "live" tone only when that leg has
 * a real (non-stale) tick. Graceful when the client is null (static export / no
 * env): the section renders a plain "connects on deploy" card — never a crash
 * or blank, and all routes prerender.
 */
import { useEffect, useRef, useState } from "react";
import { LiveBadge, PerformanceDashboard, Reveal, fmtNum, fmtPct } from "@digithings/web";
import type {
  DashboardAllocation,
  DashboardHeadline,
  DashboardRatio,
} from "@digithings/web";
import { useLivePortfolio, type LivePosition } from "@/lib/live";

/** Direction of the last change to a live value ("up"/"down"), held briefly so
 *  the cell can flash, then cleared — so a ticking price is *perceptibly* live,
 *  not just silently different. Null when nothing has changed. */
function useTickFlash(value: number | null): "up" | "down" | null {
  const prev = useRef<number | null>(value);
  const [dir, setDir] = useState<"up" | "down" | null>(null);
  useEffect(() => {
    const before = prev.current;
    prev.current = value;
    if (before == null || value == null || value === before) return;
    setDir(value > before ? "up" : "down");
    const t = setTimeout(() => setDir(null), 900);
    return () => clearTimeout(t);
  }, [value]);
  return dir;
}

/** Wraps a live read so it washes --up/--down on change (reduced-motion-safe:
 *  the wash is CSS-animation-gated, so it degrades to the final value). */
function FlashNum({
  value,
  className = "",
  children,
}: {
  value: number | null;
  className?: string;
  children: React.ReactNode;
}) {
  const dir = useTickFlash(value);
  return (
    <span className={`dq-tick${dir ? ` dq-tick-${dir}` : ""}${className ? ` ${className}` : ""}`}>
      {children}
    </span>
  );
}

/** Signed percent read with an explicit "+" on gains; em dash for missing. */
function signedPct(v: number | null): string {
  if (v == null) return "—";
  return (v > 0 ? "+" : "") + fmtPct(v);
}

/** P&L text tone utility for a signed value (money colors, direction only). */
function toneText(v: number | null): string {
  if (v == null || v === 0) return "text-ink-soft";
  return v > 0 ? "text-up" : "text-down";
}

/** Adaptive price precision so a $525 ETF and a $28 one both read cleanly. */
function fmtPrice(v: number | null): string {
  if (v == null) return "—";
  return Math.abs(v) >= 1000 ? fmtNum(v, 0) : fmtNum(v, 2);
}

function SectionShell({ children }: { children: React.ReactNode }) {
  return (
    <section className="section" id="live-portfolio" aria-label="Live research portfolio">
      <div className="wrap">
        <Reveal>
          <div style={{ textAlign: "center" }}>
            <span className="kicker">{"// olympus · live book"}</span>
            <h2 className="dq-title">The research book, valued live.</h2>
            <p className="dq-sub" style={{ marginInline: "auto" }}>
              The paper portfolio Atlas and Hermes maintain, marked against the same price
              feed. Positions and weights are the published book; prices tick live during
              market hours, and P&amp;L is stated as of the last close.
            </p>
          </div>
        </Reveal>
        <div className="mx-auto mt-[2.2rem] max-w-[900px]">{children}</div>
      </div>
    </section>
  );
}

/** Muted single-card state (loading / empty / error / unconfigured). */
function NoticeCard({ children }: { children: React.ReactNode }) {
  return (
    <div className="rounded-[12px] border border-hair bg-surface px-[1.4rem] py-[1.6rem] text-center font-mono text-[0.82rem] text-ink-mute">
      {children}
    </div>
  );
}

function PositionsTable({ positions }: { positions: LivePosition[] }) {
  const rows = [...positions].sort((a, b) => b.weightPct - a.weightPct);
  return (
    <div className="mt-[1.1rem] overflow-x-auto rounded-[12px] border border-hair bg-surface">
      <table className="w-full min-w-[560px] border-collapse font-mono text-[0.8rem] [font-variant-numeric:tabular-nums]">
        <thead>
          <tr className="border-b border-hair">
            {["ticker", "sleeve", "weight", "price", "day", "since entry"].map((h, i) => (
              <th
                key={h}
                className={`px-4 py-[0.7rem] text-[0.56rem] font-normal uppercase tracking-[0.1em] text-ink-mute ${
                  i <= 1 ? "text-left" : "text-right"
                }`}
              >
                {h}
              </th>
            ))}
          </tr>
        </thead>
        <tbody>
          {rows.map((p) => (
            <tr key={p.ticker} className="border-b border-hair/60 last:border-b-0">
              <td className="px-4 py-[0.6rem] text-left text-ink">
                <span className="inline-flex items-center gap-2">
                  {p.ticker}
                  {p.isLive ? <LiveBadge ariaLabel={`${p.ticker} price is live`} /> : null}
                </span>
              </td>
              <td className="px-4 py-[0.6rem] text-left text-ink-mute">{p.sectorBucket ?? "—"}</td>
              <td className="px-4 py-[0.6rem] text-right text-ink-soft">
                {fmtNum(p.weightPct, 1)}%
              </td>
              <td
                className={`px-4 py-[0.6rem] text-right ${p.isLive ? "text-ink" : "text-ink-soft"}`}
              >
                <FlashNum value={p.livePrice}>{fmtPrice(p.livePrice)}</FlashNum>
              </td>
              <td className={`px-4 py-[0.6rem] text-right ${toneText(p.dayChangePct)}`}>
                <FlashNum value={p.dayChangePct}>{signedPct(p.dayChangePct)}</FlashNum>
              </td>
              <td className={`px-4 py-[0.6rem] text-right ${toneText(p.sinceEntryReturnPct)}`}>
                <FlashNum value={p.sinceEntryReturnPct}>
                  {signedPct(p.sinceEntryReturnPct)}
                </FlashNum>
              </td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  );
}

export function OlympusPortfolioPanel() {
  const book = useLivePortfolio();
  const { configured, loading, error, positions, nav, latestNav, liveTotalValue, liveVsMarkPct } =
    book;

  if (!configured) {
    return (
      <SectionShell>
        <NoticeCard>
          <span className="text-ink">Live research portfolio</span> — connects to the price
          feed once the site is deployed with its public keys.
        </NoticeCard>
      </SectionShell>
    );
  }
  if (loading) {
    return (
      <SectionShell>
        <NoticeCard>Loading the book…</NoticeCard>
      </SectionShell>
    );
  }
  if (error || positions.length === 0) {
    return (
      <SectionShell>
        <NoticeCard>The live book is momentarily unavailable — check back shortly.</NoticeCard>
      </SectionShell>
    );
  }

  // base 100 (see docblock): since-inception is level − 100. `latestNav` is
  // sourced from the NAV series, so it is null only if that series is empty
  // (positions without NAV) — guard so the headline can never read "−100%".
  const liveNav = liveTotalValue ?? latestNav;
  const sinceInception = liveNav == null ? null : liveNav - 100;
  const latest = nav.length > 0 ? nav[nav.length - 1] : null;
  const liveCount = positions.filter((p) => p.isLive).length;
  const investable = positions.filter((p) => p.ticker !== "CASH");

  const headlines: DashboardHeadline[] = [
    {
      label: "portfolio NAV",
      value: fmtNum(liveNav, 2),
      note:
        sinceInception == null
          ? "base 100 · paper index"
          : `${signedPct(sinceInception)} since inception · base 100`,
      noteTone:
        sinceInception == null
          ? undefined
          : sinceInception > 0
            ? "up"
            : sinceInception < 0
              ? "down"
              : undefined,
    },
    {
      label: "live vs last close",
      value: signedPct(liveVsMarkPct),
      tone: liveVsMarkPct > 0 ? "up" : liveVsMarkPct < 0 ? "down" : undefined,
      note:
        liveCount > 0
          ? `${liveCount} of ${investable.length} legs live`
          : "market closed · marked at close",
    },
  ];

  const ratios: DashboardRatio[] = [
    { label: "invested", value: `${fmtNum(latest?.investedPct ?? null, 0)}%` },
    { label: "cash", value: `${fmtNum(latest?.cashPct ?? null, 0)}%` },
    { label: "positions", value: String(investable.length) },
    {
      label: "prior day",
      value: signedPct(latest?.dayReturnPct ?? null),
      tone:
        (latest?.dayReturnPct ?? 0) > 0 ? "up" : (latest?.dayReturnPct ?? 0) < 0 ? "down" : undefined,
    },
  ];

  const allocations: DashboardAllocation[] = [...positions]
    .sort((a, b) => b.weightPct - a.weightPct)
    .map((p) => ({ name: p.ticker, pct: Math.round(p.weightPct) }));

  const asOf = positions.find((p) => p.metricsAsOf)?.metricsAsOf ?? book.metricsAsOf;

  return (
    <SectionShell>
      <div className="mb-[1.1rem] flex flex-wrap items-center justify-center gap-x-[0.9rem] gap-y-[0.4rem]">
        <LiveBadge label="live research portfolio" ariaLabel="Live research portfolio" />
        {asOf ? (
          <span className="font-mono text-[0.68rem] uppercase tracking-[0.1em] text-ink-mute">
            marks as of {asOf}
          </span>
        ) : null}
      </div>

      <PerformanceDashboard
        headlines={headlines}
        ratios={ratios}
        ratioColumns={4}
        allocations={allocations}
        allocationsLabel="book weights"
      />

      <PositionsTable positions={positions} />

      <p className="mx-auto mt-[0.9rem] max-w-[640px] text-center font-mono text-[0.64rem] text-ink-mute">
        Research/paper portfolio — not a live-traded fund. Prices tick live during US market
        hours; positions, weights and P&amp;L are stated as of the last published close.
      </p>
    </SectionShell>
  );
}
