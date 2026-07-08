"use client";
/**
 * Homepage strategy spotlight — scroll-pinned peek stack (BTC / ETH / SOL).
 *
 * Cards slide in from below as you scroll; the full stack + library CTA scale to
 * fit the viewport when zoom or content height would otherwise clip.
 *
 * Scroll handling (#1322): measurement (layout reads + height/scale writes) runs
 * only when something can actually change size — mount, resize, visualViewport,
 * ResizeObserver on the pin column/stack, tearsheet data landing — and caches
 * its results in a ref. The per-scroll path is Motion's `useScroll` progress →
 * pure math on the cached metrics → setState. Cards are memoized so scroll
 * frames re-render only the transform wrappers, never the charts.
 */
import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  useSyncExternalStore,
  type CSSProperties,
  type ReactNode,
  type RefObject,
} from "react";
// Hooks only — the same import the shared scrolly primitive (@digithings/web
// motion/scrolly.tsx) uses internally; hooks don't pull the full animation
// runtime. Element creators must come from @digithings/web's `m` (the app is
// wrapped in LazyMotion strict, which throws on a full `motion.*` component).
import { useScroll, useMotionValueEvent } from "motion/react";
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
const MIN_FIT_SCALE = 0.68;

type PreviewMode = "charts" | "tables";

const clamp = (v: number, lo: number, hi: number) => Math.max(lo, Math.min(hi, v));

const emptySubscribe = () => () => {};

// Cached once — the per-scroll path must not re-query media state (#1322).
let reducedMq: MediaQueryList | null = null;
function prefersReducedMotion(): boolean {
  if (typeof window === "undefined") return false;
  reducedMq ??= window.matchMedia("(prefers-reduced-motion: reduce)");
  return reducedMq.matches;
}

function easeInOutCubic(t: number): number {
  const x = clamp(t, 0, 1);
  return x < 0.5 ? 4 * x * x * x : 1 - (-2 * x + 2) ** 3 / 2;
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

function cardEnterBudgetsPx(scrolly: HTMLElement, count: number): number[] {
  const base = parseCssLengthPx(
    getComputedStyle(scrolly).getPropertyValue("--dqss-enter-scroll").trim() || "80svh",
    window.innerHeight,
  );
  if (count <= 0) return [];
  if (count === 1) return [base];
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

const StrategyTearsheetCard = memo(function StrategyTearsheetCard({
  entry,
}: {
  entry: StrategyIndexEntry;
}) {
  const cardRef = useRef<HTMLDivElement>(null);
  const cardWidth = useElementWidth(cardRef);
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
        <div className="dqss-preview-pane">
          {mode === "charts" ? (
            <div className="dqss-preview-pane-layer dqss-preview-chart-pane">
              <div className="ts-chart dqss-preview-chart">
                {chartLoading ? (
                  <div className="dqss-chart-skeleton" aria-hidden="true" />
                ) : chartReady ? (
                  <CandlestickChart
                    bars={chartOhlc}
                    trades={previewTrades}
                    height={PREVIEW_PANE_H}
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
          ) : (
            <div className="dqss-preview-pane-layer dqss-preview-table-pane">
              {data ? (
                <PivotStatsTable data={data} pivot="direction" compact />
              ) : (
                <p className="dqss-chart-empty">Loading statistics…</p>
              )}
            </div>
          )}
        </div>
      </section>

      <p className="dqss-preview-footer">
        <Link className="dqss-full" href={`/strategies/${entry.strategy}`}>
          View full tearsheet ↗
        </Link>
      </p>
    </div>
  );
});

function navHeightPx(): number {
  const raw = getComputedStyle(document.documentElement).getPropertyValue("--dq-nav-h").trim();
  const parsed = Number.parseFloat(raw);
  return Number.isFinite(parsed) ? parsed : 0;
}

function peekHeightPx(stack: HTMLElement | null): number {
  const raw = getComputedStyle(stack ?? document.documentElement)
    .getPropertyValue("--dqss-peek")
    .trim();
  const parsed = Number.parseFloat(raw);
  if (!Number.isFinite(parsed)) return 60;
  return raw.endsWith("rem") ? parsed * 16 : parsed;
}

function tallestCardHeightPx(scrolly: HTMLElement): number {
  let tallest = 0;
  scrolly.querySelectorAll<HTMLElement>(".dqss-card").forEach((card) => {
    tallest = Math.max(tallest, card.offsetHeight);
  });
  return tallest > 0 ? tallest : 620;
}

function libraryCtaHideOffsetPx(scrolly: HTMLElement): number {
  const cta = scrolly.querySelector<HTMLElement>(".dqss-library-cta");
  return (cta?.offsetHeight ?? 52) + 40;
}

function syncStackHeight(scrolly: HTMLElement, count: number): number {
  const stack = scrolly.querySelector<HTMLElement>(".dqss-stack");
  if (!stack) return 620;
  const cardH = tallestCardHeightPx(scrolly);
  const peek = peekHeightPx(stack);
  const stackH = cardH + peek * Math.max(0, count - 1) + 16;
  stack.style.setProperty("--dqss-card-h", `${cardH}px`);
  stack.style.height = `${stackH}px`;
  const clip = scrolly.querySelector<HTMLElement>(".dqss-stack-clip");
  if (clip) clip.style.height = `${stackH}px`;
  return stackH;
}

function applyViewportFit(scrolly: HTMLElement, count: number): void {
  const col = scrolly.querySelector<HTMLElement>(".dqss-pin-col");
  const stack = scrolly.querySelector<HTMLElement>(".dqss-stack");
  if (!col) return;

  col.style.setProperty("--dqss-fit-scale", "1");
  if (stack) stack.style.removeProperty("--dqss-peek");

  syncStackHeight(scrolly, count);

  const available = window.innerHeight - navHeightPx() - 24;
  let contentH = col.scrollHeight;
  if (contentH <= available) return;

  let scale = clamp(available / contentH, MIN_FIT_SCALE, 1);
  if (stack && scale < 0.92) {
    stack.style.setProperty("--dqss-peek", scale < 0.8 ? "2.35rem" : "2.75rem");
    syncStackHeight(scrolly, count);
    contentH = col.scrollHeight;
    scale = clamp(available / contentH, MIN_FIT_SCALE, 1);
  }
  col.style.setProperty("--dqss-fit-scale", scale.toFixed(4));
}

function totalScrollyHeightPx(scrolly: HTMLElement, pinH: number, count: number): number {
  const viewportMin = Math.max(320, window.innerHeight - navHeightPx());
  const pinRunway = Math.max(pinH, viewportMin);
  const style = getComputedStyle(scrolly);
  const introHold = parseCssLengthPx(style.getPropertyValue("--dqss-intro-hold").trim(), window.innerHeight);
  const ctaScroll = parseCssLengthPx(style.getPropertyValue("--dqss-cta-scroll").trim(), window.innerHeight);
  const budgetSum = totalCardBudgetPx(cardEnterBudgetsPx(scrolly, count));
  const tail = 0.32 * window.innerHeight;
  return Math.ceil(introHold + budgetSum + ctaScroll + pinRunway + tail);
}

function syncScrollyHeight(scrolly: HTMLElement, pinH: number, count: number): void {
  const reduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  if (reduced) {
    scrolly.style.height = "";
    return;
  }
  const heightPx = totalScrollyHeightPx(scrolly, pinH, count);
  scrolly.style.height = `${heightPx}px`;
}

function measureStackMetrics(scrolly: HTMLElement, count: number) {
  const pin = scrolly.querySelector<HTMLElement>(".dqss-stack-pin");
  const stackH = syncStackHeight(scrolly, count);
  applyViewportFit(scrolly, count);
  const pinH = pin?.getBoundingClientRect().height ?? Math.max(320, window.innerHeight - navHeightPx());
  syncScrollyHeight(scrolly, pinH, count);
  const pinHAfter = pin?.getBoundingClientRect().height ?? pinH;
  const scrollable = Math.max(1, scrolly.offsetHeight - pinHAfter);
  const hideOffset = stackH + 24;
  const ctaHideOffset = libraryCtaHideOffsetPx(scrolly);
  return { pinH: pinHAfter, scrollable, hideOffset, ctaHideOffset, stackH };
}

/** Everything the per-scroll math needs, produced by the measure pass only. */
type StackMetrics = {
  scrollable: number;
  hideOffset: number;
  ctaHideOffset: number;
  budgets: number[];
  ctaBudget: number;
  holdPx: number;
  /** Window-scroll distance the scrolly spans (height − viewport) — maps
   *  Motion's 0..1 progress back to scrolled pixels. */
  runway: number;
};

export function StrategySuite() {
  const scrollyRef = useRef<HTMLDivElement>(null);
  const metricsRef = useRef<StackMetrics | null>(null);
  const [activeIndex, setActiveIndex] = useState(0);
  const [cardOffsets, setCardOffsets] = useState<number[]>(() => STRATEGIES.map(() => 9999));
  const [introPhase, setIntroPhase] = useState(true);
  const [libraryCtaOffset, setLibraryCtaOffset] = useState(9999);
  // aria-hidden is a JS-driven visual-sync concern: SSR must not ship it, or
  // no-JS screen-reader users lose the deck entirely (law 06). Applied only
  // after hydration (the DqNav mount-gate idiom); the wrappers suppress the
  // attribute-level mismatch.
  const hydrated = useSyncExternalStore(
    emptySubscribe,
    () => true,
    () => false,
  );
  const count = STRATEGIES.length;

  const { scrollYProgress } = useScroll({
    target: scrollyRef,
    offset: ["start start", "end end"],
  });

  useEffect(() => {
    prefetchAllTearsheets(STRATEGIES.map((s) => s.strategy));
  }, []);

  // Per-scroll path: pure math on cached metrics — zero layout reads or writes.
  const applyScroll = () => {
    const m = metricsRef.current;
    if (!m) return;
    const scrolled = clamp(scrollYProgress.get() * m.runway, 0, m.scrollable);

    if (scrolled < m.holdPx) {
      setIntroPhase(true);
      setActiveIndex(0);
      setCardOffsets(STRATEGIES.map(() => m.hideOffset));
      setLibraryCtaOffset(m.ctaHideOffset);
      return;
    }

    setIntroPhase(false);
    const scrolledPastHold = scrolled - m.holdPx;

    if (prefersReducedMotion()) {
      const idx = stackActiveIndex(scrolledPastHold, m.budgets);
      setActiveIndex(idx);
      setCardOffsets(STRATEGIES.map((_, i) => (i <= idx ? 0 : m.hideOffset)));
      setLibraryCtaOffset(
        scrolledPastHold >= totalCardBudgetPx(m.budgets) ? 0 : m.ctaHideOffset,
      );
      return;
    }

    setActiveIndex(stackActiveIndex(scrolledPastHold, m.budgets));
    setCardOffsets(
      STRATEGIES.map((_, i) => stackCardOffsetY(i, scrolledPastHold, m.budgets, m.hideOffset)),
    );
    setLibraryCtaOffset(
      libraryCtaOffsetY(scrolledPastHold, m.budgets, m.ctaBudget, m.ctaHideOffset),
    );
  };
  const applyScrollRef = useRef(applyScroll);
  useEffect(() => {
    applyScrollRef.current = applyScroll;
  });

  useMotionValueEvent(scrollYProgress, "change", () => applyScrollRef.current());

  useEffect(() => {
    const scrolly = scrollyRef.current;
    if (!scrolly) return;

    // Measure pass: all layout reads + height/scale writes live here. Runs on
    // mount, viewport changes, pin column / stack resizes, and tearsheet data
    // landing — never on scroll (#1322).
    const remeasure = () => {
      const { scrollable, hideOffset, ctaHideOffset } = measureStackMetrics(scrolly, count);
      metricsRef.current = {
        scrollable,
        hideOffset,
        ctaHideOffset,
        budgets: cardEnterBudgetsPx(scrolly, count),
        ctaBudget: libraryCtaBudgetPx(scrolly),
        holdPx: introHoldPx(scrolly),
        runway: Math.max(1, scrolly.offsetHeight - window.innerHeight),
      };
      applyScrollRef.current();
    };

    const nudgeStrategiesHash = () => {
      if (window.location.hash !== "#strategies") return;
      const m = metricsRef.current;
      if (!m) return;
      const scrolled = clamp(-scrolly.getBoundingClientRect().top, 0, m.scrollable);
      if (scrolled >= m.holdPx) return;
      window.scrollTo({
        top: window.scrollY + (m.holdPx - scrolled) + 1,
        behavior: "instant",
      });
    };

    const onHashChange = () => {
      requestAnimationFrame(() => {
        remeasure();
        nudgeStrategiesHash();
      });
    };

    const onViewportChange = () => {
      remeasure();
    };

    window.addEventListener("resize", onViewportChange, { passive: true });
    window.addEventListener("hashchange", onHashChange);
    window.visualViewport?.addEventListener("resize", onViewportChange);
    window.visualViewport?.addEventListener("scroll", onViewportChange);

    const col = scrolly.querySelector<HTMLElement>(".dqss-pin-col");
    const stack = scrolly.querySelector<HTMLElement>(".dqss-stack");
    const ro = new ResizeObserver(() => {
      requestAnimationFrame(remeasure);
    });
    if (col) ro.observe(col);
    if (stack) ro.observe(stack);

    remeasure();
    requestAnimationFrame(() => {
      remeasure();
      nudgeStrategiesHash();
    });

    const unsubCache = subscribeTearsheetCache(() => {
      requestAnimationFrame(remeasure);
    });

    return () => {
      unsubCache();
      window.removeEventListener("resize", onViewportChange);
      window.removeEventListener("hashchange", onHashChange);
      window.visualViewport?.removeEventListener("resize", onViewportChange);
      window.visualViewport?.removeEventListener("scroll", onViewportChange);
      ro.disconnect();
    };
    // applyScrollRef is stable; remeasure closes over the current count.
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

            <div className="dqss-stack-clip" aria-hidden={hydrated ? introPhase : undefined}>
              <div
                className="dqss-stack"
                role="group"
                aria-roledescription="carousel"
                aria-label={`Strategy tearsheets — ${symbolBase(STRATEGIES[activeIndex]?.symbol ?? "BTC")} on top`}
              >
                {STRATEGIES.map((entry, i) => {
                  const offset = cardOffsets[i] ?? 0;
                  const notYetShown = introPhase || (offset > 8 && i !== activeIndex);
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
                      aria-hidden={hydrated ? introPhase || i > activeIndex : undefined}
                    >
                      <StrategyTearsheetCard entry={entry} />
                    </div>
                  );
                })}
              </div>
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
    </section>
  );
}
