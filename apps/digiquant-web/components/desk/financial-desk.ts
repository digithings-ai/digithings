/** Which desk the financial digichat session answers about. */
export type FinancialDesk = "baseline" | "fx";

export const DESK_STORAGE_KEY = "dq-desk";
export const DESK_CHANGE_EVENT = "dq-desk";

/**
 * FX Hub wins when the page is an FX path or the caller has that desk selected.
 * Every other page is the baseline desk run.
 */
export function financialDesk(path: string, stored: string | null): FinancialDesk {
  if (path === "/fx" || path.startsWith("/fx/")) return "fx";
  if (stored === "fx") return "fx";
  return "baseline";
}

export function financialDeskLabel(desk: FinancialDesk): string {
  return desk === "fx" ? "FX Hub" : "baseline desk run";
}
