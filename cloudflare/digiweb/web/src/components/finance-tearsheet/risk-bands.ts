/**
 * Composite-risk bands for DCA / SDCA tearsheets (#3172).
 *
 * The artifact's scale is 0–100 (cheap → rich). Labels match the published
 * SDCA bands: Fire sale / Accumulate / Value / Above mid / Hot / Bubble.
 * 95–100 is Bubble (the spec's 95–99 band plus the closed top of the scale).
 */

export interface RiskBand {
  /** Inclusive lower bound. */
  lo: number;
  /** Exclusive upper bound, except the last band which includes 100. */
  hi: number;
  id: "fire" | "acc" | "value" | "mid" | "hot" | "bubble";
  label: string;
}

export const RISK_BANDS: readonly RiskBand[] = [
  { lo: 0, hi: 10, id: "fire", label: "Fire sale" },
  { lo: 10, hi: 25, id: "acc", label: "Accumulate" },
  { lo: 25, hi: 50, id: "value", label: "Value" },
  { lo: 50, hi: 75, id: "mid", label: "Above mid" },
  { lo: 75, hi: 95, id: "hot", label: "Hot" },
  { lo: 95, hi: 100, id: "bubble", label: "Bubble" },
] as const;

/** Band copy for a composite risk in [0, 100]. Null/NaN → null. */
export function riskBandLabel(risk: number | null | undefined): string | null {
  if (risk === null || risk === undefined || Number.isNaN(risk)) return null;
  if (risk < 10) return "Fire sale";
  if (risk < 25) return "Accumulate";
  if (risk < 50) return "Value";
  if (risk < 75) return "Above mid";
  if (risk < 95) return "Hot";
  return "Bubble";
}

/** Today's-rate sentence for a DCA current signal. */
export function dcaRateCopy(dailyRatePct: number | null | undefined): string | null {
  if (dailyRatePct === null || dailyRatePct === undefined || Number.isNaN(dailyRatePct)) {
    return null;
  }
  const abs = Math.abs(dailyRatePct).toLocaleString("en-US", {
    minimumFractionDigits: 1,
    maximumFractionDigits: 1,
  });
  if (dailyRatePct > 0) return `buying ${abs}% of remaining cash today`;
  if (dailyRatePct < 0) return `selling ${abs}% of remaining holdings today`;
  return "holding, no trade today";
}
