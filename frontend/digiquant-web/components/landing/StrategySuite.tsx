"use client";
/**
 * Vertical scrollytelling strategy suite (ported from v7), wired to REAL data.
 *
 * The left column lists the published strategies from `public/strategies/index.json`.
 * A sticky card on the right swaps as you scroll (IntersectionObserver) or on
 * click, and renders the REAL backtest: a log equity sparkline with real trade
 * markers (fetched from `/strategies/<id>.json`, the same files the full
 * tearsheet uses), real KPIs from the index entry, and the most recent real
 * trades. No simulated/random data — v7's `rnd()`/`series()` are dropped.
 * "No live prices" forbids a live tape, not these static backtest JSONs.
 */
import { useEffect, useRef, useState } from "react";
import { fmtMoney, fmtNum, fmtPct } from "@/components/tearsheet/format";
import { type StrategyIndexEntry, type TearsheetData } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

// stable display order (majors): BTC → ETH → SOL
const RANK: Record<string, number> = { btc_slapper: 0, eth_slapper: 1, sol_slapper: 2 };
const STRATS = (index as StrategyIndexEntry[])
  .slice()
  .sort((a, b) => (RANK[a.strategy] ?? 99) - (RANK[b.strategy] ?? 99));

// editorial one-liners (copy; the figures themselves come from the real entry)
const DESC: Record<string, string> = {
  btc_slapper:
    "A regime-switching trend system on bitcoin — long and short across eight years of data, with an 8.7× profit factor.",
  eth_slapper:
    "The same engine on ether — fewer, larger swings and a 6.6× profit factor across the full cycle.",
  sol_slapper:
    "Solana since 2021 — higher volatility, a 3.6× profit factor, and drawdowns to match the upside.",
};

const base = (symbol: string) => symbol.split("-")[0];
const signed = (v: number) => (v > 0 ? "+" : "") + fmtPct(v);

function Logo({ id }: { id: string }) {
  if (id === "btc_slapper")
    return (
      <svg viewBox="0 0 24 24" fill="#f7931a" aria-hidden="true">
        <path d="M12 2a10 10 0 100 20 10 10 0 000-20zm4.3 8.6c-.2 1.3-1 1.8-2.1 2 .8.3 1.3.9 1.1 2.1-.2 1.5-1.4 1.9-3 1.9l-.4 1.6-1-.2.4-1.6-.8-.2-.4 1.6-1-.2.4-1.6-2-.5.5-1.2s.7.2.7.2c.3.1.4-.1.5-.3l1-4.1c0-.3 0-.5-.4-.6 0 0-.7-.2-.7-.2l.3-1.1 2.1.5.4-1.5 1 .2-.4 1.5.8.2.4-1.5 1 .2-.4 1.6c1.4.3 2.4.8 2.2 2.3zm-2.3.5c.2-.9-1.2-1.1-1.7-1.2l-.5 1.9c.5.1 2 .3 2.2-.7zm-.5 2.9c.2-1-1.5-1.2-2-1.3l-.5 2.1c.6.1 2.3.3 2.5-.8z" />
      </svg>
    );
  if (id === "eth_slapper")
    return (
      <svg viewBox="0 0 24 24" fill="#8a92b2" aria-hidden="true">
        <path d="M12 2l6 10-6 3.5L6 12z" />
        <path fill="#62688f" d="M12 16.8l6-3.5-6 8.7-6-8.7z" />
      </svg>
    );
  return (
    <svg viewBox="0 0 24 24" fill="#14F195" aria-hidden="true">
      <path d="M6 7h11l-2 2H6zM6 11h11v2H6zM8 16h11l-2-2H8z" />
    </svg>
  );
}

/** Read a CSS color token resolved to rgb() (handles `var()` chains reliably). */
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

/** Fraction (0..1) of `date` along the (date-sorted) curve. ISO dates compare lexically. */
function dateFrac(curve: TearsheetData["equity_curve"], date: string): number {
  const n = curve.length;
  if (n < 2) return 1;
  if (date <= curve[0].t) return 0;
  if (date >= curve[n - 1].t) return 1;
  let lo = 0;
  let hi = n - 1;
  while (lo < hi) {
    const mid = (lo + hi) >> 1;
    if (curve[mid].t < date) lo = mid + 1;
    else hi = mid;
  }
  return lo / (n - 1);
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
  const UP = readColor("var(--up)");
  const DOWN = readColor("var(--down)");
  const BG = readColor("var(--bg)");
  const pad = 10;

  // downsample for the line; log scale absorbs the huge compounded range
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

  // real trade markers: last 6 trades, placed by exit date, coloured by side
  data.trades.slice(-6).forEach((t) => {
    const k = Math.round(dateFrac(curve, t.exit_date) * (ld.length - 1));
    c.beginPath();
    c.arc(X(k), Y(ld[k]), 4, 0, 7);
    c.fillStyle = t.direction === "long" ? UP : DOWN;
    c.fill();
    c.strokeStyle = BG;
    c.lineWidth = 1.5;
    c.stroke();
  });
}

export function StrategySuite() {
  const [activeId, setActiveId] = useState(STRATS[0].strategy);
  const [data, setData] = useState<TearsheetData | null>(null);
  const cache = useRef<Map<string, TearsheetData>>(new Map());
  const itemEls = useRef<(HTMLDivElement | null)[]>([]);
  const canvasRef = useRef<HTMLCanvasElement>(null);

  const entry = STRATS.find((s) => s.strategy === activeId) ?? STRATS[0];

  // fetch (and cache) the real tearsheet JSON for the active strategy
  useEffect(() => {
    let alive = true;
    const cached = cache.current.get(activeId);
    if (cached) {
      setData(cached);
      return;
    }
    setData(null);
    fetch(`/strategies/${activeId}.json`)
      .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
      .then((d: TearsheetData) => {
        if (!alive) return;
        cache.current.set(activeId, d);
        setData(d);
      })
      .catch(() => {
        if (alive) setData(null);
      });
    return () => {
      alive = false;
    };
  }, [activeId]);

  // (re)draw the equity sparkline when the data or viewport changes
  useEffect(() => {
    if (!data || !canvasRef.current) return;
    const draw = () => canvasRef.current && drawChart(canvasRef.current, data);
    draw();
    window.addEventListener("resize", draw, { passive: true });
    return () => window.removeEventListener("resize", draw);
  }, [data]);

  // scroll drives the active strategy (centre band)
  useEffect(() => {
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
  }, []);

  const select = (id: string) => {
    const el = itemEls.current.find((e) => e?.dataset.id === id);
    el?.scrollIntoView({ behavior: "smooth", block: "center" });
    setActiveId(id);
  };

  const kpis: [string, string, string][] = [
    ["Net profit", signed(entry.net_profit_pct), "is-pos"],
    ["Profit factor", fmtNum(entry.profit_factor, 2), ""],
    ["Win rate", fmtPct(entry.win_rate_pct), ""],
    ["Max DD", fmtPct(entry.max_drawdown_pct), "is-neg"],
  ];
  const recent = data ? data.trades.slice(-6).reverse() : [];

  return (
    <section className="dqss" id="strategies">
      <div className="wrap">
        <div className="dqss-intro">
          <div className="dq-eyebrow">The suite · long / short</div>
          <h2 className="dq-title">The book, marked to market.</h2>
          <p className="dq-sub">
            Long/short systems on crypto majors, backtested on NautilusTrader — each with a full
            tearsheet and every fill marked on the chart.
          </p>
        </div>

        <div className="dqss-grid">
          <div className="dqss-left">
            {STRATS.map((s, i) => (
              <div
                key={s.strategy}
                className={`dqss-item${s.strategy === activeId ? " active" : ""}`}
                data-id={s.strategy}
                role="button"
                tabIndex={0}
                aria-pressed={s.strategy === activeId}
                ref={(el) => {
                  itemEls.current[i] = el;
                }}
                onClick={() => select(s.strategy)}
                onKeyDown={(e) => {
                  if (e.key === "Enter" || e.key === " ") {
                    e.preventDefault();
                    select(s.strategy);
                  }
                }}
              >
                <div className="dqss-tag">
                  <span className="dqss-logo">
                    <Logo id={s.strategy} />
                  </span>
                  {s.symbol} · NautilusTrader
                </div>
                <h3>{s.label ?? s.strategy}</h3>
                <p>{DESC[s.strategy] ?? "NautilusTrader backtest."}</p>
                <span className="dqss-dir">{signed(s.net_profit_pct)} net</span>
              </div>
            ))}
          </div>

          <aside className="dqss-right">
            <div className="dqss-card">
              <div className="dqss-card-bar">
                <span>
                  {entry.label ?? entry.strategy} · {entry.symbol}
                </span>
                <span>
                  {entry.period_start} → {entry.period_end}
                </span>
              </div>
              <div className="dqss-card-body">
                <canvas className="dqss-chart" ref={canvasRef} />
                <div className="dqss-legend">
                  <span>
                    <i style={{ background: "var(--up)" }} />
                    long
                  </span>
                  <span>
                    <i style={{ background: "var(--down)" }} />
                    short
                  </span>
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
                    recent.map((t) => (
                      <div className="dqss-fill" key={t.n}>
                        <span className={`side ${t.direction === "long" ? "is-pos" : "is-neg"}`}>
                          {t.direction === "long" ? "LONG" : "SHORT"}
                        </span>
                        <span>
                          {base(entry.symbol)} {fmtMoney(t.exit_price)}
                        </span>
                        <span className={t.pnl_pct >= 0 ? "is-pos" : "is-neg"}>
                          {t.pnl_pct >= 0 ? "+" : ""}
                          {fmtNum(t.pnl_pct, 1)}%
                        </span>
                      </div>
                    ))
                  ) : (
                    <p className="dqss-empty">Loading backtest…</p>
                  )}
                </div>
                <a className="dqss-full" href={`/strategies/${entry.strategy}`}>
                  View full tearsheet ↗
                </a>
              </div>
            </div>
          </aside>
        </div>
      </div>
    </section>
  );
}
