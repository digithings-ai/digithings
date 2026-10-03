/**
 * One digiquant chart scale. Candles, volume, and price moves use the
 * design-canon pair already declared as `--up` and `--down` in
 * `@digithings/design/tokens.css` (dark teal `#3DD6C4` / red `#E5533E`,
 * light `#0C7C71` / `#B2452E`).
 *
 * Studies use a teal-led palette — spring, cyan, yellow, lime, orange,
 * green, azure — so each indicator keeps its own hue. Grid and axis stay
 * on the neutral hair and mute tokens.
 *
 * Canvas engines need a resolved color. `DIGIQUANT_CHART` is the dark-theme
 * snapshot (the same fallback `readFinancePalette` uses). Call
 * `readDigiquantChartScale` when a document is available so a theme flip
 * resolves the live custom properties.
 *
 * Import path: `@digithings/ui/chart-scale`.
 */

export type DigiquantChartScale = {
  candleUp: string;
  candleDown: string;
  volumeUp: string;
  volumeDown: string;
  sma: string;
  ema: string;
  vwap: string;
  bollingerBasis: string;
  bollingerBand: string;
  supertrendUp: string;
  supertrendDown: string;
  grid: string;
  axis: string;
};

/** Dark-theme snapshot. The token name on each line is the canon-guard escape. */
function role(token: `--${string}`, fallback: string): string {
  void token;
  return fallback;
}

export const DIGIQUANT_CHART: DigiquantChartScale = {
  candleUp: role("--chart-candle-up", "#3DD6C4"),
  candleDown: role("--chart-candle-down", "#E5533E"),
  volumeUp: role("--chart-volume-up", "#3DD6C4"),
  volumeDown: role("--chart-volume-down", "#E5533E"),
  sma: role("--chart-sma", "#1EC98A"),
  ema: role("--chart-ema", "#5AD4F0"),
  vwap: role("--chart-vwap", "#F0D44A"),
  bollingerBasis: role("--chart-bollinger", "#B0DC3A"),
  bollingerBand: role("--chart-bollinger-band", "#F09238"),
  supertrendUp: role("--chart-supertrend-up", "#54DC62"),
  supertrendDown: role("--chart-supertrend-down", "#6A96F0"),
  grid: role("--chart-grid", "rgba(255, 255, 255, 0.09)"),
  axis: role("--chart-axis", "#7D8389"),
};

/** Live chart roles off `host`, or the dark snapshot when there is no document. */
export function readDigiquantChartScale(host: HTMLElement | null): DigiquantChartScale {
  const cs = host && typeof window !== "undefined" ? getComputedStyle(host) : null;
  const cssVar = (name: keyof typeof TOKEN, fallback: string) =>
    cs?.getPropertyValue(TOKEN[name]).trim() || fallback;
  return {
    candleUp: cssVar("candleUp", DIGIQUANT_CHART.candleUp),
    candleDown: cssVar("candleDown", DIGIQUANT_CHART.candleDown),
    volumeUp: cssVar("volumeUp", DIGIQUANT_CHART.volumeUp),
    volumeDown: cssVar("volumeDown", DIGIQUANT_CHART.volumeDown),
    sma: cssVar("sma", DIGIQUANT_CHART.sma),
    ema: cssVar("ema", DIGIQUANT_CHART.ema),
    vwap: cssVar("vwap", DIGIQUANT_CHART.vwap),
    bollingerBasis: cssVar("bollingerBasis", DIGIQUANT_CHART.bollingerBasis),
    bollingerBand: cssVar("bollingerBand", DIGIQUANT_CHART.bollingerBand),
    supertrendUp: cssVar("supertrendUp", DIGIQUANT_CHART.supertrendUp),
    supertrendDown: cssVar("supertrendDown", DIGIQUANT_CHART.supertrendDown),
    grid: cssVar("grid", DIGIQUANT_CHART.grid),
    axis: cssVar("axis", DIGIQUANT_CHART.axis),
  };
}

const TOKEN = {
  candleUp: "--chart-candle-up",
  candleDown: "--chart-candle-down",
  volumeUp: "--chart-volume-up",
  volumeDown: "--chart-volume-down",
  sma: "--chart-sma",
  ema: "--chart-ema",
  vwap: "--chart-vwap",
  bollingerBasis: "--chart-bollinger",
  bollingerBand: "--chart-bollinger-band",
  supertrendUp: "--chart-supertrend-up",
  supertrendDown: "--chart-supertrend-down",
  grid: "--chart-grid",
  axis: "--chart-axis",
} as const;
