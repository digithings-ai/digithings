"use client";
/**
 * Vertical scrollytelling strategy suite (ported from v7), wired to REAL data.
 *
 * Desktop: left column lists strategies; sticky tearsheet on the right swaps on
 * scroll (IntersectionObserver) or click.
 *
 * Mobile: sequential pairs — strategy copy, then its tearsheet — no sticky card
 * or scroll-driven swapping.
 */
import { type KeyboardEvent, useEffect, useRef, useState } from "react";
import Link from "next/link";
import { AssetLogoFor } from "@/components/tearsheet/asset-logo";
import { directionLabel } from "@/components/tearsheet/direction-label";
import { LiveMetricsBadge } from "@/components/tearsheet/live-metrics";
import { fmtNum, fmtPct } from "@/components/tearsheet/format";
import { avgTradePct, cagrPctFromGrowth } from "@/components/tearsheet/stats";
import { sortTradesForLog, isOpenTrade, markPriceForTrade, openTrade, tradesForDisplay, unrealizedReturnPct } from "@/components/tearsheet/trades";
import { symbolBase } from "@/components/tearsheet/strategy-names";
import { type StrategyIndexEntry, type TearsheetData } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

const DESKTOP_MQ = "(min-width: 861px)";

// stable display order (majors): BTC → ETH → SOL
const RANK: Record<string, number> = { btc_slapper: 0, eth_slapper: 1, sol_slapper: 2 };
const STRATS = (index as StrategyIndexEntry[])
  .slice()
  .sort((a, b) => (RANK[a.strategy] ?? 99) - (RANK[b.strategy] ?? 99));

function strategyBlurb(s: StrategyIndexEntry): string {
  const cagr = cagrPctFromGrowth(s.net_profit_pct, s.period_start, s.period_end);
  const asset = symbolBase(s.symbol);
  const pf = s.profit_factor ?? 0;
  return `long/short on ${asset} · ${fmtPct(cagr)} CAGR · ${fmtNum(pf, 2)}× profit factor · ${fmtNum(s.total_trades)} trades.`;
}

const tearsheetCache = new Map<string, TearsheetData>();

const base = symbolBase;
const signed = (v: number) => (v > 0 ? "+" : "") + fmtPct(v);

function readColor(expr: string): string {
  const probe = document.createElement("span");
  probe.style.cssText = `color:${expr};position:absolute;left:-9999px`;
  document.body.appendChild(probe);
  const c = getComputedStyle(probe).color;
  probe.remove();
  return c || "rgb(61,214,196)";
}

function withAlpha(rgb: string, a: number): string {
  const m = rgb.match(/[\d.]+/g);
  if (!m || m.length < 3) return rgb;
  return `rgba(${m[0]}, ${m[1]}, ${m[2]}, ${a})`;
}

function drawChart(canvas: HTMLCanvasElement, data: TearsheetData) {
  const curve = data.equity_curve;
  if (!curve || curve.length === 0) return;
  const dpr = window.devicePixelRatio || 1;
  const w = canvas.clientWidth;
  const h = canvas.clientHeight;
  if (!w || !h) return;
  canvas.width = Math.round(w * dpr);
  canvas.height = Math.round(h * dpr);
  const c = canvas.getContext("2d");
  if (!c) return;
  c.setTransform(dpr, 0, 0, dpr, 0, 0);
  c.clearRect(0, 0, w, h);

  const ACC = readColor("var(--accent)");
  const pad = 10;

  const N = 160;
  const ds = curve.length <= N ? curve : Array.from({ length: N }, (_, i) => curve[Math.floor((i * curve.length) / N)]);
  if (ds[ds.length - 1] !== curve[curve.length - 1]) ds.push(curve[curve.length - 1]);
  const ld = ds.map((p) => Math.log(Math.max(p.v, 1e-9)));
  const mn = Math.min(...ld);
  const mx = Math.max(...ld);
  const X = (k: number) => pad + (k * (w - 2 * pad)) / (ld.length - 1);
  const Y = (v: number) => h - pad - ((v - mn) / (mx - mn || 1)) * (h - 2 * pad);

  const g = c.createLinearGradient(0, 0, 0, h);
  g.addColorStop(0, withAlpha(ACC, 0.16));
  g.addColorStop(1, withAlpha(ACC, 0));
  c.beginPath();
  c.moveTo(X(0), h - pad);
  ld.forEach((v, k) => c.lineTo(X(k), Y(v)));
  c.lineTo(X(ld.length - 1), h - pad);
  c.closePath();
  c.fillStyle = g;
  c.fill();

  c.beginPath();
  ld.forEach((v, k) => (k ? c.lineTo(X(k), Y(v)) : c.moveTo(X(k), Y(v))));
  c.strokeStyle = ACC;
  c.lineWidth = 2;
  c.stroke();
}

function useTearsheetData(strategyId: string) {
  const [data, setData] = useState<TearsheetData | null>(() => tearsheetCache.get(strategyId) ?? null);

  useEffect(() => {
    const cached = tearsheetCache.get(strategyId);
    if (cached) {
      setData(cached);
      return;
    }
    let alive = true;
    setData(null);
    fetch(`/strategies/${strategyId}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: TearsheetData) => {
        if (!alive) return;
        tearsheetCache.set(strategyId, d);
        setData(d);
      })
      .catch(() => {
        if (alive) setData(null);
      });
    return () => {
      alive = false;
    };
  }, [strategyId]);

  return data;
}

function StrategyBlurb({
  s,
  active = false,
  interactive = false,
  onSelect,
  itemRef,
}: {
  s: StrategyIndexEntry;
  active?: boolean;
  interactive?: boolean;
  onSelect?: () => void;
  itemRef?: (el: HTMLDivElement | null) => void;
}) {
  const ann = cagrPctFromGrowth(s.net_profit_pct, s.period_start, s.period_end);
  const className = `dqss-item${active ? " active" : ""}${interactive ? "" : " dqss-item-static"}`;

  return (
    <div
      className={className}
      data-id={s.strategy}
      ref={itemRef}
      {...(interactive
        ? {
            role: "button",
            tabIndex: 0,
            "aria-pressed": active,
            onClick: onSelect,
            onKeyDown: (e: KeyboardEvent) => {
              if (e.key === "Enter" || e.key === " ") {
                e.preventDefault();
                onSelect?.();
              }
            },
          }
        : {})}
    >
      <div className="dqss-tag">
        <span className="dqss-logo">
          <AssetLogoFor strategy={s.strategy} symbol={s.symbol} size={26} />
        </span>
        <LiveMetricsBadge generatedAt={s.generated_at} className="dqss-live" />
      </div>
      <h3>{symbolBase(s.symbol)}</h3>
      <p>{strategyBlurb(s)}</p>
      <span className="dqss-dir">{signed(ann)} ann.</span>
    </div>
  );
}

function StrategyTearsheetCard({ entry }: { entry: StrategyIndexEntry }) {
  const data = useTearsheetData(entry.strategy);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const draw = () => canvasRef.current && drawChart(canvasRef.current, data);
    draw();
    window.addEventListener("resize", draw, { passive: true });
    return () => window.removeEventListener("resize", draw);
  }, [data]);

  const cagr = cagrPctFromGrowth(entry.net_profit_pct, entry.period_start, entry.period_end);
  const kpis: [string, string, string][] = [
    ["Annualized", signed(cagr), "is-pos"],
    ["Avg trade", data ? signed(avgTradePct(data.trades.map((t) => t.pnl_pct))) : "—", ""],
    ["Win rate", fmtPct(entry.win_rate_pct), ""],
    ["Max DD", fmtPct(entry.max_drawdown_pct), "is-neg"],
  ];
  const recent = data ? sortTradesForLog(tradesForDisplay(data)).slice(0, 6) : [];

  return (
    <div className="dqss-card">
      <div className="dqss-card-bar">
        <span className="dqss-card-title">
          <AssetLogoFor strategy={entry.strategy} symbol={entry.symbol} size={24} />
          {symbolBase(entry.symbol)}
        </span>
        <span className="dqss-card-bar-meta">
          <LiveMetricsBadge generatedAt={entry.generated_at} />
          <span>
            {entry.period_start} → {entry.period_end}
          </span>
        </span>
      </div>
      <div className="dqss-card-body">
        <canvas className="dqss-chart" ref={canvasRef} />
        <div className="dqss-legend">
          <span>
            <i style={{ background: "var(--accent)" }} />
            equity (log)
          </span>
        </div>
        <div className="dqss-kpis">
          {kpis.map(([l, v, tone]) => (
            <div className="dqss-kpi" key={l}>
              <div className="l">{l}</div>
              <div className={`v ${tone}`}>{v}</div>
            </div>
          ))}
        </div>
        <div className="dqss-fills">
          <h6>Recent trades · {fmtNum(entry.total_trades)} total</h6>
          {recent.length ? (
            recent.map((t) => {
              const open = isOpenTrade(t);
              const mark = data ? markPriceForTrade(t, data) : t.exit_price;
              const ret = open && data ? unrealizedReturnPct(t, mark) : t.pnl_pct;
              return (
              <div className="dqss-fill" key={t.n}>
                <span className={`side ${t.direction === "long" ? "is-pos" : "is-neg"}`}>
                  {directionLabel(t.direction)}
                </span>
                <span>
                  {base(entry.symbol)}{" "}
                  {fmtNum(open ? t.entry_price : t.exit_price, 2)}
                  {open ? ` → ${fmtNum(mark, 2)}` : ""}
                </span>
                <span className={open ? (ret >= 0 ? "is-pos" : "is-neg") : ret >= 0 ? "is-pos" : "is-neg"}>
                  {open
                    ? `${ret >= 0 ? "+" : ""}${fmtNum(ret, 1)}% unrealized`
                    : `${ret >= 0 ? "+" : ""}${fmtNum(ret, 1)}%`}
                </span>
              </div>
            );
            })
          ) : (
            <p className="dqss-empty">Loading backtest…</p>
          )}
        </div>
        <a className="dqss-full" href={`/strategies/${entry.strategy}`}>
          View full tearsheet ↗
        </a>
      </div>
    </div>
  );
}

export function StrategySuite() {
  const [activeId, setActiveId] = useState(STRATS[0].strategy);
  const itemEls = useRef<(HTMLDivElement | null)[]>([]);

  const entry = STRATS.find((s) => s.strategy === activeId) ?? STRATS[0];

  // Desktop only: scroll drives the active strategy (centre band)
  useEffect(() => {
    const mq = window.matchMedia(DESKTOP_MQ);
    const attach = () => {
      if (!mq.matches) return () => {};
      const io = new IntersectionObserver(
        (entries) =>
          entries.forEach((e) => {
            if (e.isIntersecting) {
              const id = (e.target as HTMLElement).dataset.id;
              if (id) setActiveId(id);
            }
          }),
        { rootMargin: "-45% 0px -45% 0px", threshold: 0 },
      );
      itemEls.current.forEach((el) => el && io.observe(el));
      return () => io.disconnect();
    };

    let cleanup = attach();
    const onChange = () => {
      cleanup();
      cleanup = attach();
    };
    mq.addEventListener("change", onChange);
    return () => {
      mq.removeEventListener("change", onChange);
      cleanup();
    };
  }, []);

  const select = (id: string) => {
    const el = itemEls.current.find((e) => e?.dataset.id === id);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    setActiveId(id);
  };

  return (
    <section className="dqss" id="strategies">
      <div className="wrap">
        <div className="dqss-intro">
          <div className="dq-eyebrow">The suite · long / short</div>
          <h2 className="dq-title">The book, marked to market.</h2>
          <p className="dq-sub">
            Flagship long/short systems on crypto majors — equity, drawdown, and the full trade log.
          </p>
          <Link href="/strategies" className="dqss-lib-link">
            Strategy library →
          </Link>
        </div>

        <div className="dqss-grid dqss-desktop">
          <div className="dqss-left">
            {STRATS.map((s, i) => (
              <StrategyBlurb
                key={s.strategy}
                s={s}
                active={s.strategy === activeId}
                interactive
                onSelect={() => select(s.strategy)}
                itemRef={(el) => {
                  itemEls.current[i] = el;
                }}
              />
            ))}
          </div>

          <aside className="dqss-right">
            <StrategyTearsheetCard entry={entry} />
          </aside>
        </div>

        <div className="dqss-stack dqss-mobile" aria-label="Strategy tearsheets">
          {STRATS.map((s) => (
            <article key={s.strategy} className="dqss-pair">
              <StrategyBlurb s={s} />
              <StrategyTearsheetCard entry={s} />
            </article>
          ))}
        </div>
      </div>
    </section>
  );
}
