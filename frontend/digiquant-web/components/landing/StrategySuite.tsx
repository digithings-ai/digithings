"use client";
/**
 * Homepage strategy spotlight — the BTC / ETH / SOL tearsheet previews on the
 * canonical <DeckStack/> sticky cascade (@digithings/web, promoted from the
 * design reference's card deck, #1450).
 *
 * The previous bespoke scroll carousel (a .dqss-stack clip box + JS-measured
 * per-card offsets and a buried/top/hidden state machine) hard-clipped buried
 * cards mid-content at its overflow:hidden boundary. The deck pattern has no
 * clip box, no fixed card height and no shadow: every card is fully rendered
 * in normal document flow, pins under the nav at a cascaded top offset
 * (--stack-index), and the next opaque card covering it IS the seam — nothing
 * is ever cut off, and the content reads top-to-bottom with no JS. The deck
 * mechanics live in @digithings/web/styles/deck.css (imported from
 * globals.css, with the components/deck @source line); this file only owns
 * the tearsheet-preview card content and its data loading.
 */
import {
  memo,
  useEffect,
  useMemo,
  useRef,
  useState,
  type ReactNode,
  type RefObject,
} from "react";
import Link from "next/link";
import {
  CandlestickChart,
  DeckCard,
  DeckStack,
  KpiStrip,
  SegToggle,
  fmtNum,
  fmtPct,
  toneClass,
  viewWindowForPreset,
} from "@digithings/web";
import { AssetLogoFor } from "@/components/tearsheet/asset-logo";
import { CurrentPosition } from "@/components/tearsheet/current-position";
import { LiveMetricsBadge } from "@/components/tearsheet/live-metrics";
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

function useElementWidth(ref: RefObject<HTMLElement | null>): number {
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

/** Family-shaped KPI cell (.ts-kpi grammar) with one extra: the dqss
 *  container-query hide classes (dqss-kpi-medium / dqss-kpi-optional) ride
 *  the cell itself, and the family Kpi takes no className — so the preview
 *  keeps this local wiring instead of degrading the responsive KPI ladder. */
function Kpi({ label, value, className }: { label: string; value: ReactNode; className?: string }) {
  return (
    <div className={"ts-kpi" + (className ? ` ${className}` : "")}>
      <span className="ts-kpi-label">{label}</span>
      <span className="ts-kpi-value">{value}</span>
    </div>
  );
}

/**
 * One tearsheet preview card body — header, current position, KPIs,
 * chart/table toggle. Rendered inside a <DeckCard className="dqss-card">
 * (the deck card element carries the .dqss-card dress + container queries);
 * the width probe rides the header, which spans the card's content box.
 */
const StrategyTearsheetCard = memo(function StrategyTearsheetCard({
  entry,
}: {
  entry: StrategyIndexEntry;
}) {
  const headerRef = useRef<HTMLElement>(null);
  const cardWidth = useElementWidth(headerRef);
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
    <>
      <header ref={headerRef} className="ts-header">
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

      <KpiStrip primary ariaLabel="Headline performance">
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
      </KpiStrip>

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
    </>
  );
});

export function StrategySuite() {
  useEffect(() => {
    prefetchAllTearsheets(STRATEGIES.map((s) => s.strategy));
  }, []);

  return (
    <section className="section dqss" id="strategies">
      <div className="wrap">
        <div className="dqss-intro">
          <div className="dqss-intro-copy">
            <span className="kicker">{"// pre-built strategy library"}</span>
            <h2 className="dq-title">Research-grade systems, ready to explore.</h2>
            <p className="dq-sub">
              Browse calibrated backtests from the DigiQuant library — equity, drawdown, trade
              logs, and full tearsheets for every release. More assets join the catalog as they
              clear the pipeline.
            </p>
          </div>
          <Link href="/strategies" className="dqss-library-pill">
            Full strategy library
            <span className="dqss-library-arrow" aria-hidden="true">
              →
            </span>
          </Link>
        </div>

        <DeckStack
          ariaLabel="Strategy tearsheets"
          rail={STRATEGIES.map((s) => symbolBase(s.symbol))}
        >
          {STRATEGIES.map((entry) => (
            <DeckCard key={entry.strategy} className="dqss-card">
              <StrategyTearsheetCard entry={entry} />
            </DeckCard>
          ))}
        </DeckStack>
      </div>
    </section>
  );
}
