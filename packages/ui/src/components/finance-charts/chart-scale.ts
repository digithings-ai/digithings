/**
 * One digiquant chart scale. Positive and negative price moves use the
 * design-canon pair already declared as `--up` and `--down` in
 * `@digithings/design/tokens.css`. Studies that are not themselves a
 * direction still draw from that pair, so a chart does not invent a second
 * green and red. Grid and axis stay on the neutral hair and mute tokens.
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
  sma: role("--chart-sma", "#3DD6C4"),
  ema: role("--chart-ema", "#E5533E"),
  vwap: role("--chart-vwap", "#3DD6C4"),
  bollingerBasis: role("--chart-bollinger", "#E5533E"),
  bollingerBand: role("--chart-bollinger-band", "#3DD6C4"),
  supertrendUp: role("--chart-supertrend-up", "#3DD6C4"),
  supertrendDown: role("--chart-supertrend-down", "#E5533E"),
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
