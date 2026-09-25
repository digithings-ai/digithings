/**
 * Navigable pipeline cards for expanded mosaic tiles (#4429, restart).
 *
 * One module at a time: each card turns the kit `Pipeline` into that
 * module's public tool surface — every node is a real tool or tool group,
 * selecting it shows what it does and what it takes. Definition-mode
 * throughout: no wall time, tokens, or cost is ever printed (a marketing
 * card has no measured run, and numbers would fake a benchmark).
 *
 * Only digiquant ships for now (Stage 3 builds one card as the example);
 * the other ten specs are approved and waiting, not started.
 */
import type { PipelineColumn, PipelineSummaryItem } from "../components/effects-chrome";

export interface PipelineCardSnippet {
  label: string;
  code: string;
}

export interface PipelineCardData {
  id: string;
  kicker: string;
  title: string;
  lede: string;
  badges: string[];
  /** Small mono line under the lede (strategy lineup, ports…). */
  sub?: string;
  /** Always-visible honesty note (paper-only, roadmap…). */
  notice?: string;
  columns: PipelineColumn[];
  summary: PipelineSummaryItem[];
  defaultSelectedId: string;
  snippet: PipelineCardSnippet[];
  snippetCaption: string;
  proof: string[];
  connects: string[];
  /** Extra honesty line under the detail panel, keyed by node id. */
  foot: Record<string, string>;
  /** Motif class on the card root (per-module look). */
  motifClass: string;
}

/** digiquant — the example card. 18 nodes, 5 columns, all shipped. */
export const digiquantCard: PipelineCardData = {
  id: "digiquant",
  kicker: "DIGIQUANT / QUANT ENGINE",
  title: "Own your quant engine.",
  lede: "Self-hosted quant engine: NautilusTrader backtests, Optuna tuning, and published tearsheets you own.",
  badges: ["SELF-HOSTED", "PAPER-ONLY — NO LIVE TRADING", "58 TOOLS · 44 READ"],
  sub: "strategies: slappers · sdca · rotation · classics",
  notice: "Brokers are paper-only. Live trading is not shipped.",
  columns: [
    {
      id: "registry",
      kind: "step",
      nodes: [
        {
          id: "list_strategies",
          label: "list_strategies",
          status: "done",
          note: "Browse the strategy registry. No params.",
          outputs: "registry names + metadata",
          model: "polars",
        },
      ],
    },
    {
      id: "market-data",
      kind: "parallel",
      label: "parallel · 5 — market data",
      nodes: [
        {
          id: "get_price_technicals",
          label: "get_price_technicals",
          status: "done",
          note: "Price + technicals for one ticker.",
          inputs: "ticker",
          outputs: "ohlcv + indicators",
          model: "polars",
        },
        {
          id: "get_macro_series",
          label: "get_macro_series",
          status: "done",
          note: "Macro series by id.",
          inputs: "series_ids",
          outputs: "series values",
          model: "polars",
        },
        {
          id: "get_trade_levels",
          label: "get_trade_levels",
          status: "done",
          note: "Read-only support / resistance levels.",
          inputs: "direction",
          outputs: "levels (read-only)",
          model: "polars",
        },
        {
          id: "query_data",
          label: "query_data",
          status: "done",
          note: "Direct table query with filters.",
          inputs: "table + filters + limit",
          outputs: "rows",
          model: "polars",
        },
        {
          id: "digifetch_family",
          label: "digifetch_quotes…",
          status: "done",
          note: "digifetch family: 34 quote / history / screener / filings tools as one fan-out. Examples inside.",
          inputs: "symbol / query",
          outputs: "quotes · bars · screens · filings",
          model: "polars",
        },
      ],
    },
    {
      id: "provisioners",
      kind: "parallel",
      label: "parallel · 6 — provisioners",
      nodes: [
        {
          id: "fetch_coinbase_ohlcv",
          label: "fetch_coinbase_ohlcv",
          status: "done",
          note: "Provisioner. Pull Coinbase OHLCV bars.",
          inputs: "symbol + granularity",
          outputs: "ohlcv bars",
          model: "polars",
        },
        {
          id: "fetch_bars_bundle",
          label: "fetch_bitview+bgeometrics+coinmetrics",
          status: "done",
          note: "Provisioner. Remote bar bundles: bitview / bgeometrics / coinmetrics.",
          inputs: "symbol + range",
          outputs: "ohlcv bundles",
          model: "polars",
        },
        {
          id: "list_coinmetrics_catalog",
          label: "list_coinmetrics_catalog",
          status: "done",
          note: "Provisioner. Browse the CoinMetrics catalog.",
          outputs: "catalog entries",
          model: "polars",
        },
        {
          id: "fit_btc_power_law",
          label: "fit_btc_power_law",
          status: "done",
          note: "Provisioner. Fit BTC power-law trend model.",
          inputs: "price history",
          outputs: "model fit",
          model: "polars",
        },
        {
          id: "build_sdca_risk_index",
          label: "build_sdca_risk_index",
          status: "done",
          note: "Provisioner. Build the SDCA risk index.",
          inputs: "market inputs",
          outputs: "risk index",
          model: "polars",
        },
        {
          id: "fit_sdca_weights",
          label: "fit_sdca_weights",
          status: "done",
          note: "Provisioner. Fit SDCA allocation weights.",
          inputs: "risk inputs",
          outputs: "weights",
          model: "optuna",
        },
      ],
    },
    {
      id: "engine",
      kind: "step",
      nodes: [
        {
          id: "run_backtest",
          label: "run_backtest",
          status: "done",
          note: "NautilusTrader backtest. The hero node.",
          inputs: "strategy_name + symbols_json",
          outputs: "run + metrics + artifacts",
          model: "nautilus",
        },
        {
          id: "run_optimize",
          label: "run_optimize",
          status: "done",
          note: "Optuna / grid / random parameter search.",
          inputs: "strategy + method + n_trials",
          outputs: "ranked trials",
          model: "optuna",
        },
        {
          id: "run_export",
          label: "run_export",
          status: "done",
          note: "Export a strategy package for review.",
          inputs: "target: nautilus / tradingview / alpaca / quantconnect",
          outputs: "export bundle",
          model: "nautilus",
        },
        {
          id: "run_pipeline",
          label: "run_pipeline",
          status: "done",
          note: "One command: validate, backtest, optimize, export.",
          inputs: "strategy + data",
          outputs: "run + trials + export",
          model: "nautilus · optuna",
        },
      ],
    },
    {
      id: "publish",
      kind: "step",
      nodes: [
        {
          id: "generate_slapper_tearsheet",
          label: "generate_slapper_tearsheet",
          status: "done",
          note: "Publish a tearsheet you own.",
          inputs: "backtest run",
          outputs: "tearsheet (static publish)",
          model: "polars",
        },
        {
          id: "policy_replay_gate",
          label: "policy_replay+gate",
          status: "done",
          note: "Minor. Five dashboard policy replay / gate tools grouped in one node.",
          inputs: "run + policy",
          outputs: "replay + gate verdict",
          model: "polars",
        },
      ],
    },
  ],
  summary: [
    { label: "engines", value: "nautilus · optuna · polars" },
    { label: "strategies", value: "slappers · sdca · rotation · classics" },
    { label: "execution", value: "paper-only" },
    { label: "tearsheets", value: "published · you own" },
  ],
  defaultSelectedId: "run_backtest",
  snippet: [
    { label: "start the stack", code: "compose up digiquant" },
    {
      label: "run a backtest",
      code: "backtest --strategy <registry-name> --symbols '[\"BTC-USD\"]'",
    },
  ],
  snippetCaption: "Swap in any registry name from list_strategies. Paper/simulated only.",
  proof: [
    "Tearsheets publish as static surfaces you host.",
    "NAV / tearsheet surfaces refresh on a 3-day delay.",
    "Paper-only brokers — live trading is not shipped.",
  ],
  connects: [
    "digigraph invokes digiquant tools.",
    "Tearsheets / NAV publish out.",
    "digiclaw audits runs.",
  ],
  foot: {
    list_strategies: "Registry names are display strings, not performance claims.",
    digifetch_family:
      "Examples: quote lookup · price history · stock screener · filings search. Full 34-tool list lives in product docs.",
    run_backtest: "Paper/simulated only.",
    policy_replay_gate: "Detail omitted on card; one-line summary only.",
  },
  motifClass: "m-pipe--tearsheet",
};

/** Cards keyed by module id. Only digiquant for now — the rest on approval. */
export const pipelineCards: Record<string, PipelineCardData> = {
  digiquant: digiquantCard,
};
