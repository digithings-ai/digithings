"use client";
/**
 * Homepage strategy spotlight — scroll-pinned card stack (BTC / ETH / SOL).
 *
 * Scroll progress slides each tearsheet up over the previous one.
 */
import {
  useEffect,
  useMemo,
  useRef,
  useState,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
import Link from "next/link";
import { AssetLogoFor } from "@/components/tearsheet/asset-logo";
import { CurrentPosition } from "@/components/tearsheet/current-position";
import { LiveMetricsBadge } from "@/components/tearsheet/live-metrics";
import { CandlestickChart, SegToggle, viewWindowForPreset } from "@/components/tearsheet/charts";
import { fmtNum, fmtPct, toneClass } from "@/components/tearsheet/format";
import { PivotStatsTable } from "@/components/tearsheet/pivot-stats-table";
import { chartFullSpan, clipOhlc } from "@/components/tearsheet/series";
import { avgTradePct, cagrPct, tradesPerYear } from "@/components/tearsheet/stats";
import { symbolBase } from "@/components/tearsheet/strategy-names";
import { type StrategyIndexEntry, type TearsheetData } from "@/components/tearsheet/types";
import index from "@/public/strategies/index.json";

const SLAPPER_ORDER = ["btc_slapper", "eth_slapper", "sol_slapper"] as const;
const ALL_STRATS = index as StrategyIndexEntry[];
const STRATEGIES = SLAPPER_ORDER.map(
  (id) => ALL_STRATS.find((s) => s.strategy === id) ?? ALL_STRATS[0],
).filter(Boolean) as StrategyIndexEntry[];

const PREVIEW_PANE_H = 220;
const PREVIEW_LOOKBACK = "6m" as const;

type PreviewMode = "charts" | "tables";

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

/** Smooth ease — slow start and end so cards glide in rather than snap. */
function easeInOutCubic(t: number): number {
  const x = clamp(t, 0, 1);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
}

/** Scroll distance (px) allocated to each card's bottom-to-seat entrance. */
function cardEnterBudgetsPx(scrolly: HTMLElement, count: number): number[] {
  const base = parseCssLengthPx(
    getComputedStyle(scrolly).getPropertyValue("--dqss-enter-scroll").trim() || "80svh",
    window.innerHeight,
  );
  if (count <= 0) return [];
  if (count === 1) return [base];
  // First card still leads, but every entrance gets a long scroll runway.
  return Array.from({ length: count }, (_, i) => (i === 0 ? base * 0.82 : base * 1.12));
}

function stackCardOffsetY(
  cardIndex: number,
  scrolledPastHold: number,
  budgets: number[],
  hideOffset: number,
): number {
  let cursor = 0;
  for (let i = 0; i < budgets.length; i++) {
    const budget = budgets[i]!;
    const start = cursor;
    cursor += budget;
    if (i !== cardIndex) continue;
    if (scrolledPastHold <= start) return hideOffset;
    if (scrolledPastHold >= cursor) return 0;
    const t = (scrolledPastHold - start) / budget;
    return hideOffset * (1 - easeInOutCubic(t));
  }
  return hideOffset;
}

function stackActiveIndex(scrolledPastHold: number, budgets: number[]): number {
  let cursor = 0;
  let idx = 0;
  for (let i = 0; i < budgets.length; i++) {
    if (scrolledPastHold >= cursor) idx = i;
    cursor += budgets[i]!;
  }
  return idx;
}

function totalCardBudgetPx(budgets: number[]): number {
  return budgets.reduce((sum, b) => sum + b, 0);
}

function libraryCtaBudgetPx(scrolly: HTMLElement): number {
  return parseCssLengthPx(
    getComputedStyle(scrolly).getPropertyValue("--dqss-cta-scroll").trim() || "40svh",
    window.innerHeight,
  );
}

function libraryCtaOffsetY(
  scrolledPastHold: number,
  cardBudgets: number[],
  ctaBudget: number,
  hideOffset: number,
): number {
  const cardsEnd = totalCardBudgetPx(cardBudgets);
  if (scrolledPastHold <= cardsEnd) return hideOffset;
  const ctaEnd = cardsEnd + ctaBudget;
  if (scrolledPastHold >= ctaEnd) return 0;
  const t = (scrolledPastHold - cardsEnd) / ctaBudget;
  return hideOffset * (1 - easeInOutCubic(t));
}

function parseCssLengthPx(raw: string, viewportH: number): number {
  const trimmed = raw.trim();
  if (!trimmed) return 0;
  const n = Number.parseFloat(trimmed);
  if (!Number.isFinite(n)) return 0;
  if (trimmed.endsWith("svh") || trimmed.endsWith("vh")) return (n / 100) * viewportH;
  if (trimmed.endsWith("rem")) return n * 16;
  return n;
}

function introHoldPx(scrolly: HTMLElement): number {
  const raw = getComputedStyle(scrolly).getPropertyValue("--dqss-intro-hold").trim();
  return parseCssLengthPx(raw, window.innerHeight);
}

function useElementWidth(ref: RefObject<HTMLDivElement | null>): number {
  const [width, setWidth] = useState(640);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const ro = new ResizeObserver(([entry]) => {
      setWidth(entry.contentRect.width);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);

  return width;
}

function useElementHeight(ref: RefObject<HTMLElement | null>, fallback = PREVIEW_PANE_H): number {
  const [height, setHeight] = useState(fallback);

  useEffect(() => {
    const el = ref.current;
    if (!el) return;

    const ro = new ResizeObserver(([entry]) => {
      const next = Math.floor(entry.contentRect.height);
      if (next > 0) setHeight(next);
    });
    ro.observe(el);
    return () => ro.disconnect();
  }, [ref]);

  return height;
}

type LoadStatus = "idle" | "loading" | "loaded" | "error";

const tearsheetCache = new Map<string, TearsheetData>();
const loadStatus = new Map<string, LoadStatus>();
const inflight = new Map<string, Promise<TearsheetData | null>>();
const subscribers = new Set<() => void>();

function notifyTearsheetSubscribers() {
  subscribers.forEach((fn) => fn());
}

function subscribeTearsheetCache(fn: () => void) {
  subscribers.add(fn);
  return () => {
    subscribers.delete(fn);
  };
}

async function fetchTearsheet(strategyId: string): Promise<TearsheetData | null> {
  const cached = tearsheetCache.get(strategyId);
  if (cached) return cached;

  const pending = inflight.get(strategyId);
  if (pending) return pending;

  loadStatus.set(strategyId, "loading");
  notifyTearsheetSubscribers();

  const promise = fetch(`/strategies/${strategyId}.json`)
    .then((r) => (r.ok ? r.json() : Promise.reject(new Error(String(r.status)))))
    .then((d: TearsheetData) => {
      tearsheetCache.set(strategyId, d);
      loadStatus.set(strategyId, "loaded");
      notifyTearsheetSubscribers();
      return d;
    })
    .catch(() => {
      loadStatus.set(strategyId, "error");
      notifyTearsheetSubscribers();
      return null;
    })
    .finally(() => {
      inflight.delete(strategyId);
    });

  inflight.set(strategyId, promise);
  return promise;
}

function prefetchAllTearsheets(strategyIds: readonly string[]) {
  void Promise.all(strategyIds.map((id) => fetchTearsheet(id)));
}

function useTearsheetData(strategyId: string) {
  const [, bump] = useState(0);

  useEffect(() => subscribeTearsheetCache(() => bump((n) => n + 1)), []);

  useEffect(() => {
    void fetchTearsheet(strategyId);
  }, [strategyId]);

  const data = tearsheetCache.get(strategyId) ?? null;
  const status = loadStatus.get(strategyId) ?? (data ? "loaded" : "idle");

  return { data, status };
}

function Toned({ v, children }: { v: number | null | undefined; children: ReactNode }) {
  const c = toneClass(v);
  return c ? <span className={c}>{children}</span> : <>{children}</>;
}

function Kpi({ label, value, className }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div className={"ts-kpi" + (className ? ` ${className}` : "")}>
      <span className="ts-kpi-label">{label}</span>
      <span className="ts-kpi-value">{value}</span>
    </div>
  );
}

function StrategyTearsheetCard({ entry }: { entry: StrategyIndexEntry }) {
  const cardRef = useRef<HTMLDivElement>(null);
  const previewPaneRef = useRef<HTMLDivElement>(null);
  const cardWidth = useElementWidth(cardRef);
  const chartPaneHeight = useElementHeight(previewPaneRef);
  const [mode, setMode] = useState<PreviewMode>("charts");
  const { data, status } = useTearsheetData(entry.strategy);

  const chartOhlc = useMemo(
    () => (data?.ohlc_bars ? clipOhlc(data.ohlc_bars, data.period_start) : []),
    [data],
  );
  const fullSpan = useMemo(() => {
    if (!data) return undefined;
    return chartFullSpan(data.period_start, data.equity_curve, data.period_end);
  }, [data]);
  const view6m = useMemo(() => viewWindowForPreset(PREVIEW_LOOKBACK, fullSpan), [fullSpan]);

  const title = symbolBase(entry.symbol);
  const asset = symbolBase(entry.symbol);
  const periodStart = data?.period_start ?? entry.period_start;
  const periodEnd = data?.period_end ?? entry.period_end;

  const cagr = data
    ? cagrPct(data.initial_capital, data.final_equity, data.period_start, data.period_end)
    : 0;
  const maxDd = data?.max_drawdown_pct ?? entry.max_drawdown_pct;
  const profitFactor = data?.profit_factor ?? entry.profit_factor;
  const winRate = data?.win_rate_pct ?? entry.win_rate_pct;
  const avgTrade = data
    ? avgTradePct(data.trades.map((t) => t.pnl_pct))
    : entry.avg_trade_pct;
  const tradesYr = tradesPerYear(
    data?.total_trades ?? entry.total_trades,
    periodStart,
    periodEnd,
  );

  const chartReady = chartOhlc.length > 0;
  const chartLoading = !data && (status === "idle" || status === "loading");
  const chartUnavailable = Boolean(data) && !chartReady;
  const previewTrades = data?.trades ?? [];

  const symbol = data?.symbol ?? entry.symbol;
  const bars = data?.bars;

  return (
    <div ref={cardRef} className="dqss-card">
      <header className="ts-header dqss-card-header">
        <div className="ts-header-main">
          <h1 className="ts-h1 ts-h1-with-logo">
            <AssetLogoFor
              strategy={entry.strategy}
              symbol={entry.symbol}
              size={cardWidth >= 520 ? 32 : 28}
              className="ts-header-logo"
            />
            <span>{title}</span>
          </h1>
          <div className="ts-meta">
            <LiveMetricsBadge generatedAt={data?.generated_at ?? entry.generated_at} />
            <span className="ts-chip">{symbol}</span>
            <span className="ts-meta-text">
              {periodStart} → {periodEnd}
              {bars != null ? ` · ${fmtNum(bars)} bars` : ""}
            </span>
          </div>
        </div>
      </header>

      <div className="dqss-preview-position">
        {data ? (
          <CurrentPosition data={data} asset={asset} />
        ) : (
          <div className="dqss-position-skeleton" aria-hidden="true" />
        )}
      </div>

      <section className="ts-kpis ts-kpis-primary" aria-label="Headline performance">
        <Kpi label="CAGR" value={<Toned v={cagr}>{fmtPct(cagr)}</Toned>} />
        <Kpi label="Max drawdown" value={<span className="is-neg">{fmtPct(maxDd)}</span>} />
        <Kpi
          className="dqss-kpi-medium"
          label="Profit factor"
          value={fmtNum(profitFactor, 2)}
        />
        <Kpi className="dqss-kpi-medium" label="Win rate" value={fmtPct(winRate)} />
        <Kpi
          className="dqss-kpi-optional"
          label="Avg trade return"
          value={<Toned v={avgTrade}>{fmtPct(avgTrade)}</Toned>}
        />
        <Kpi
          className="dqss-kpi-optional"
          label="Trades / yr"
          value={fmtNum(tradesYr, 1)}
        />
      </section>

      <div className="ts-mode-bar dqss-preview-mode">
        <SegToggle
          label="Tearsheet view"
          value={mode}
          onChange={setMode}
          options={[
            { value: "charts", label: "Chart" },
            { value: "tables", label: "Table" },
          ]}
        />
      </div>

      <section
        className="ts-panel ts-tab-stack dqss-preview-panel"
        aria-label={mode === "charts" ? "Price chart" : "Statistics table"}
      >
        <div className="dqss-preview-pane" ref={previewPaneRef}>
          <div
            className="dqss-preview-pane-layer dqss-preview-chart-pane"
            hidden={mode !== "charts"}
            aria-hidden={mode !== "charts"}
          >
            <div className="ts-chart dqss-preview-chart">
              {chartLoading ? (
                <div className="dqss-chart-skeleton" aria-hidden="true" />
              ) : chartReady ? (
                  <CandlestickChart
                    bars={chartOhlc}
                    trades={previewTrades}
                    height={chartPaneHeight}
                    view={view6m}
                    fullSpan={fullSpan}
                    compact
                  />
              ) : (
                <div className="dqss-chart-empty">
                  {chartUnavailable ? "Chart unavailable" : "Could not load chart"}
                </div>
              )}
            </div>
          </div>
          <div
            className="dqss-preview-pane-layer dqss-preview-table-pane"
            hidden={mode !== "tables"}
            aria-hidden={mode !== "tables"}
          >
            {data ? (
              <PivotStatsTable data={data} pivot="direction" compact />
            ) : (
              <p className="dqss-chart-empty">Loading statistics…</p>
            )}
          </div>
        </div>
      </section>

      <p className="dqss-preview-footer">
        <Link className="dqss-full" href={`/strategies/${entry.strategy}`}>
          View full tearsheet ↗
        </Link>
      </p>
    </div>
  );
}

function navHeightPx(): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--dq-nav-h").trim();
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function peekHeightPx(scrolly: HTMLElement): number {
  const stack = scrolly.querySelector<HTMLElement>(".dqss-stack");
  const raw = getComputedStyle(stack ?? document.documentElement).getPropertyValue("--dqss-peek").trim();
  const parsed = Number.parseFloat(raw);
  if (!Number.isFinite(parsed)) return 60;
  return raw.endsWith("rem") ? parsed * 16 : parsed;
}

function measureStackMetrics(scrolly: HTMLElement) {
  const navH = navHeightPx();
  const pin = scrolly.querySelector<HTMLElement>(".dqss-stack-pin");
  const card = scrolly.querySelector<HTMLElement>(".dqss-card");
  const clip = scrolly.querySelector<HTMLElement>(".dqss-stack-clip");
  const pinH = pin?.getBoundingClientRect().height ?? Math.max(320, window.innerHeight - navH);
  const cardH = card?.offsetHeight ?? 620;
  const clipH = clip?.clientHeight ?? Math.max(280, pinH * 0.55);
  const peek = peekHeightPx(scrolly);
  const scrollable = Math.max(1, scrolly.offsetHeight - pinH);
  // Push cards fully below the clip so nothing peeks before its segment starts.
  const hideOffset = clipH + peek + 24;
  const slide = hideOffset;
  return { pinH, scrollable, slide, hideOffset, cardH };
}

export function StrategySuite() {
  const scrollyRef = useRef<HTMLDivElement>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [cardOffsets, setCardOffsets] = useState<number[]>(() => STRATEGIES.map(() => 9999));
  const [introPhase, setIntroPhase] = useState(true);
  const [libraryCtaOffset, setLibraryCtaOffset] = useState(9999);
  const count = STRATEGIES.length;

  useEffect(() => {
    prefetchAllTearsheets(STRATEGIES.map((s) => s.strategy));
  }, []);

  useEffect(() => {
    const scrolly = scrollyRef.current;
    if (!scrolly) return;

    const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;

    const updateFromScroll = () => {
      const { scrollable, hideOffset } = measureStackMetrics(scrolly);
      const budgets = cardEnterBudgetsPx(scrolly, count);
      const ctaBudget = libraryCtaBudgetPx(scrolly);
      const rect = scrolly.getBoundingClientRect();
      const scrolled = clamp(-rect.top, 0, scrollable);
      const holdPx = introHoldPx(scrolly);

      if (scrolled < holdPx) {
        setIntroPhase(true);
        setActiveIndex(0);
        setCardOffsets(STRATEGIES.map(() => hideOffset));
        setLibraryCtaOffset(hideOffset);
        return;
      }

      setIntroPhase(false);
      const scrolledPastHold = scrolled - holdPx;

      if (reduced) {
        const idx = stackActiveIndex(scrolledPastHold, budgets);
        setActiveIndex(idx);
        setCardOffsets(STRATEGIES.map((_, i) => (i <= idx ? 0 : hideOffset)));
        setLibraryCtaOffset(
          scrolledPastHold >= totalCardBudgetPx(budgets) ? 0 : hideOffset,
        );
        return;
      }

      setActiveIndex(stackActiveIndex(scrolledPastHold, budgets));
      setCardOffsets(
        STRATEGIES.map((_, i) => stackCardOffsetY(i, scrolledPastHold, budgets, hideOffset)),
      );
      setLibraryCtaOffset(
        libraryCtaOffsetY(scrolledPastHold, budgets, ctaBudget, hideOffset),
      );
    };

    window.addEventListener("scroll", updateFromScroll, { passive: true });
    window.addEventListener("resize", updateFromScroll, { passive: true });
    updateFromScroll();

    return () => {
      window.removeEventListener("scroll", updateFromScroll);
      window.removeEventListener("resize", updateFromScroll);
    };
  }, [count]);

  return (
    <section className="dqss" id="strategies">
      <div
        className="dqss-scrolly"
        ref={scrollyRef}
        style={{ "--stack-count": count } as CSSProperties}
      >
        <div className="dqss-stack-pin">
          <div className="wrap dqss-pin-col">
            <div className="dqss-intro" data-phase={introPhase ? "hold" : "stack"}>
              <span className="kicker">{"// pre-built strategy library"}</span>
              <h2 className="dq-title">Research-grade systems, ready to explore.</h2>
              <p className="dq-sub">
                Browse calibrated backtests from the DigiQuant library — equity, drawdown, trade
                logs, and full tearsheets for every release. More assets join the catalog as they
                clear the pipeline.
              </p>
            </div>

            <div className="dqss-stack-clip" aria-hidden={introPhase}>
              <div
                className="dqss-stack"
                role="group"
                aria-roledescription="carousel"
                aria-label={`Strategy tearsheets — ${symbolBase(STRATEGIES[activeIndex]?.symbol ?? "BTC")} on top`}
              >
                {STRATEGIES.map((entry, i) => {
                  const offset = cardOffsets[i] ?? 0;
                  const notYetShown =
                    introPhase || (offset > 8 && i !== activeIndex);
                  return (
                  <div
                    key={entry.strategy}
                    className="dqss-stack-card"
                    data-stack-index={i}
                    data-state={
                      notYetShown
                        ? "hidden"
                        : i < activeIndex
                          ? "buried"
                          : i === activeIndex
                            ? "top"
                            : "below"
                    }
                    style={
                      {
                        "--stack-index": i,
                        transform: `translate3d(0, ${offset}px, 0)`,
                      } as CSSProperties
                    }
                    aria-hidden={introPhase || i > activeIndex}
                  >
                    <StrategyTearsheetCard entry={entry} />
                  </div>
                  );
                })}
              </div>
              <div
                className="dqss-library-cta"
                data-state={introPhase || libraryCtaOffset > 8 ? "hidden" : "visible"}
                style={{ transform: `translate3d(0, ${libraryCtaOffset}px, 0)` }}
              >
                <Link href="/strategies" className="dqss-library-pill">
                  Full strategy library
                  <span className="dqss-library-arrow" aria-hidden="true">
                    →
                  </span>
                </Link>
              </div>
            </div>
          </div>
        </div>
      </div>
    </section>
  );
}
